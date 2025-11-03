
from dataclasses import dataclass
import json
import os

from pants.engine.console import Console
from pants.engine.fs import CreateDigest, Digest, FileContent, MergeDigests, PathGlobs, SpecsPaths
from pants.engine.goal import Goal, GoalSubsystem
from pants.engine.intrinsics import create_digest, get_digest_contents, get_digest_entries, merge_digests, path_globs_to_digest
from pants.engine.process import Process, execute_process_or_raise
from pants.engine.rules import collect_rules, concurrently, goal_rule, implicitly, rule


# This demo plugin doesn't use traditional Pants BUILD files at all.
# Instead it uses its own proprietary build directive, stored as JSON.
#
# This to demonstrate that BUILD files are a convention, not a necessity.
#
# BUILD files are useful in a variety of cases, and there is a lot of built-in support for
# them, but that support is quite heavyweight. For example, idiomatic use of them will
# materialize the entire transitive dependency graph up front, running dep inference
# logic as it goes. This may not be suitable for the real C-like project this emulates,
# since that project's dep inference is tightly bound with its build process.
# In such cases an iterative approach, as demonstrated below, may make more sense than trying
# to materialize the entire BUILD graph up front in a separate pass from the build itself.
#
# The downside is that Pants's graph querying goals (`dependents`, `dependencies`, `paths` etc.)
# won't work on this custom build format, and support would have to be added. But this is
# probably true regardless of BUILD usage since, again, figuring out the graph is, in this case,
# tightly intertwined with the build itself.
#
# So my sense is that there is an "impedance mismatch" between BUILD files as designed
# for Python, JVM etc vs this use case, and there is no need to work around it when one
# can simply cut it out entirely.
#
# If BUILD files are nonetheless desirable, it would be straightforward to use them, but
# I did want to make a point about their not being inevitable. You can invent your own
# format and still get the full benefit of the underlying Pants engine and plugin API.

_BUILD_DIRECTIVES_FILE = "build.json"


class CustomBuildError(Exception):
    pass


@dataclass(frozen=True)
class BuildResult:
    digest: Digest


@dataclass(frozen=True)
class BuildDirective:
    sources: tuple[str, ...]
    dependencies: tuple[str, ...]


@rule
async def parse_build_json(path: str) -> BuildDirective:
    digest = await path_globs_to_digest(PathGlobs((path,)))
    contents = await get_digest_contents(digest)
    if len(contents) != 1:
        raise CustomBuildError(f"Expected exactly one build.json file at {path} but got {contents}!")
    data = json.loads(contents[0].content)
    return BuildDirective(
        sources=tuple(data.get("sources", tuple())),
        dependencies=tuple(data.get("dependencies", tuple()))
    )


@rule
async def do_build(path: str) -> BuildResult:
    build_directive = await parse_build_json(path)

    # Note: In a real world case this is where we could run rules that calculate dependencies
    # dynamically from the sources (and possibly from previously-determined dependencies),
    # by running code generators, static analyzers etc.

    # Now that we have dependencies, recursively build them.
    # We're assuming there are no circular deps.
    dependency_results = await concurrently(
        do_build(os.path.join(dep_path, _BUILD_DIRECTIVES_FILE)) for dep_path in build_directive.dependencies
    )

    # Now get our own sources.
    dir = os.path.dirname(path)
    sources = await path_globs_to_digest(
        PathGlobs(os.path.join(dir, src) for src in build_directive.sources)
    )
    input_digest = await merge_digests(MergeDigests([sources, *(dr.digest for dr in dependency_results)]))
    input_entries = await get_digest_entries(input_digest)
    input_paths = [entry.path for entry in input_entries]

    # Run the process.
    proc = await execute_process_or_raise(**implicitly(
        Process(
            ["md5sum", *input_paths],
            description=f"Build {path}",
            input_digest=input_digest,
            env={"PATH": os.environ.get("PATH")},  # So the process can find md5sum.
        )
    ))
    # A real world case would likely want to do something with output files, and so we'd
    # have to set output_files/output_directories for capture on the Process object.
    # In this simple case the output is just in stdout, and we turn that into a Digest.
    md5 = proc.stdout.split()[0]
    output_path = dir.replace(os.path.sep, "_") + "_output.txt"
    output_digest = await create_digest(
        CreateDigest([FileContent(output_path, md5)])
    )
    return BuildResult(digest=output_digest)


class CustomBuildSubsystem(GoalSubsystem):
    name = "custom-build"
    help = "Custom build."


class CustomBuild(Goal):
    subsystem_cls = CustomBuildSubsystem
    environment_behavior = Goal.EnvironmentBehavior.LOCAL_ONLY


@goal_rule
async def custom_build(console: Console, specs_paths: SpecsPaths) -> CustomBuild:
    # The entry point for `pants custom-build paths/to/end/products/to/build`
    # Each specs_path can be a build.json or a directory containing one.
    paths = set()
    for path in specs_paths.files:
        if os.path.basename(path) == _BUILD_DIRECTIVES_FILE:
            paths.add(path)
    for dir in specs_paths.dirs:
        path = os.path.join(dir, _BUILD_DIRECTIVES_FILE)
        if os.path.isfile(path):
            paths.add(path)

    paths = sorted(paths)

    # TODO: Support multiple end products in a single invocation.
    #  Right now we're not doing that because everything is called "build.json", and so
    #  globbing over the entire repo would treat all the intermediate build.json as if they
    #  were end products and try to build them all concurrently, rather than in dep order.
    #  One way to differentiate would be to use a different filename for end products.
    #  Or, if it's important to be able to call `pants custom-build` directly on intermediate
    #  products, then you'd want to make sure users aren't using shell globbing to capture
    #  more than they expect.
    if len(paths) != 1:
        raise CustomBuildError(
            f"Expected exactly one build.json argument, but got: {', '.join(paths)}"
        )

    path = paths[0]
    res = await do_build(path)
    digest_contents = await get_digest_contents(res.digest)
    result = digest_contents[0].content.decode()
    console.print_stdout(console.green(f"Result for {path}: {result}"))
    return CustomBuild(exit_code=0)


def rules():
    return collect_rules()
