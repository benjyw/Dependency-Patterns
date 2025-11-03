import json
import os
from typing import Dict, List, Optional, Tuple

# Simple DFS (modified from AI-generated code) to detect cycles in the build.json graph.

UNVISITED, VISITING, VISITED = 0, 1, 2


def get_dependencies(file_path: str) -> Optional[List[str]]:
    with open(file_path, "r") as f:
        dependencies = json.load(f).get("dependencies", [])
        return [os.path.join(dep, "build.json") for dep in dependencies]


def find_cycle_in_json_graph(start_node_path: str) -> Tuple[bool, Optional[List[str]]]:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    node_states: Dict[str, int] = {}
    current_path: List[str] = []

    def dfs(current_node_path: str) -> bool:
        abs_path = os.path.abspath(os.path.join(base_dir, current_node_path))
        if node_states.get(abs_path) == VISITING:
            cycle_start_index = current_path.index(abs_path)
            cycle = current_path[cycle_start_index:] + [abs_path]
            return cycle
        if node_states.get(abs_path) == VISITED:
            return False
        node_states[abs_path] = VISITING
        current_path.append(abs_path)
        dependencies = get_dependencies(abs_path)

        if dependencies is not None:
            for dep in dependencies:
                result = dfs(dep)
                if isinstance(result, list):
                    return result

        current_path.pop()
        node_states[abs_path] = VISITED
        return False

    result = dfs(start_node_path)

    if isinstance(result, list):
        return True, result
    else:
        return False, None


if __name__ == "__main__":
    has_cycle, cycle_path = find_cycle_in_json_graph("build.json")
    if has_cycle:
        print("Cycle Detected!")
        print("Cycle Path (Absolute Paths):")
        for node in cycle_path:
            print(f"  -> {node}")
    else:
        print("No cycle found.")
