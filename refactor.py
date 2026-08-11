import os

root = r"c:\Users\liend\MEP-Agents\src"
tools_path = os.path.join(root, "tools.py")
qs_tools_path = os.path.join(root, "qs_tools.py")

with open(tools_path, "r", encoding="utf-8") as f:
    t_lines = f.readlines()

start = -1
end = -1
for i in range(len(t_lines)):
    if t_lines[i].startswith("@tool") and i+1 < len(t_lines) and t_lines[i+1].startswith("def auto_quantity_takeoff"):
        start = i
    if start != -1 and i > start + 2 and t_lines[i].startswith("@tool"):
        end = i
        break

if start != -1 and end != -1:
    func_lines = t_lines[start:end]
    new_t_lines = t_lines[:start] + t_lines[end:]
    with open(tools_path, "w", encoding="utf-8") as f:
        f.writelines(new_t_lines)
    
    with open(qs_tools_path, "a", encoding="utf-8") as f:
        f.write("\n")
        f.write("import json\nimport math\nimport pandas as pd\nfrom ezdxf import audit\nfrom src import cad_loader, cad_geometry\n")
        f.write("from src.tools import normalize_mepf_parameter_spec\n\n")
        f.writelines(func_lines)
        
    print(f"Moved {end-start} lines to qs_tools.py")
else:
    print("Could not find bounds")
