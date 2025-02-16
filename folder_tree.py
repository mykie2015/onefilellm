import os
import xml.etree.ElementTree as ET

def generate_tree_from_xml(xml_file):
    """
    Parses the given XML file (a .txt file with XML syntax) and returns a
    plain text hierarchical tree view. It rebuilds the directory structure based
    on each <file> element's "name" attribute.
    """
    try:
        tree = ET.parse(xml_file)
    except ET.ParseError as e:
        print(f"Error parsing {xml_file}: {e}")
        return ""
    root = tree.getroot()
    
    output_lines = []
    # Print root node label. Use the root's tag or type attribute if available.
    root_label = root.get("type", root.tag)
    if root.get("path"):
        root_label += f" ({root.get('path')})"
    output_lines.append(root_label)
    
    # Build hierarchical structure from flat file elements.
    tree_dict = {}
    for file_elem in root.findall("file"):
        file_path = file_elem.get("name")
        if not file_path:  # If no file name, skip.
            continue
        parts = file_path.split("/")  # Assumes "/" as path separator.
        current = tree_dict
        # Traverse/create tree for directory parts.
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        # Append file to the __files__ list.
        current.setdefault("__files__", []).append(parts[-1])
    
    def print_tree(current, prefix=""):
        # List directories and files separately.
        dirs = sorted([key for key in current.keys() if key != "__files__"])
        files = sorted(current.get("__files__", []))
        total = len(dirs) + len(files)
        for idx, key in enumerate(dirs):
            is_last = (idx == total - 1) if not files else False
            branch = "└── " if is_last and (not files) else "├── "
            output_lines.append(prefix + branch + key)
            new_prefix = prefix + ("    " if branch == "└── " else "│   ")
            print_tree(current[key], new_prefix)
        for j, filename in enumerate(files):
            # Determine if file is the last overall in this level.
            is_last = (j == len(files) - 1)
            branch = "└── " if is_last else "├── "
            output_lines.append(prefix + branch + filename)
    
    print_tree(tree_dict)
    return "\n".join(output_lines)

def process_folder(folder_path):
    tree_txt_path = os.path.join(folder_path, "tree.txt")
    # Skip processing if tree.txt exists.
    if os.path.exists(tree_txt_path):
        print(f"tree.txt exists in {folder_path}, skipping parsing.")
        return

    # Updated file: using uncompressed_output.txt (with XML syntax).
    xml_file = os.path.join(folder_path, "uncompressed_output.txt")
    if not os.path.exists(xml_file):
        print(f"uncompressed_output.txt not found in {folder_path}, skipping.")
        return

    tree_text = generate_tree_from_xml(xml_file)
    if tree_text:
        with open(tree_txt_path, "w") as f:
            f.write(tree_text)
        print(f"Generated tree.txt in {folder_path}")
    else:
        print(f"Failed to generate tree from {xml_file}")

def main():
    outputs_folder = os.path.join(os.getcwd(), "outputs")
    if not os.path.exists(outputs_folder):
        print("outputs folder not found!")
        return

    for item in os.listdir(outputs_folder):
        folder_path = os.path.join(outputs_folder, item)
        if os.path.isdir(folder_path) and item.startswith("github"):
            process_folder(folder_path)

if __name__ == "__main__":
    main()