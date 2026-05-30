
import os
import shutil
import time
import re

# --- Configuration ---
SOURCE_DIR = r"D:\工作相关\自动化\Research\V2\Reports"
DEST_VAULT_ROOT = r"D:\生活相关\笔记文件\ob\backup\自动报告"

def sync_reports():
    """
    Syncs markdown reports from SOURCE_DIR to DEST_VAULT_ROOT.
    
    Logic:
    1. Folders named 'YYYYMMDD' (8 digits) -> DEST_VAULT_ROOT\daily\YYYYMMDD
    2. Folder named 'deepdive' -> DEST_VAULT_ROOT\deepdive
    3. Other folders are skipped for now.
    """
    if not os.path.exists(SOURCE_DIR):
        print(f"Error: Source directory not found: {SOURCE_DIR}")
        return

    # Ensure destination root exists
    if not os.path.exists(DEST_VAULT_ROOT):
        try:
            os.makedirs(DEST_VAULT_ROOT)
            print(f"Created destination root: {DEST_VAULT_ROOT}")
        except OSError as e:
            print(f"Error creating destination root: {e}")
            return

    files_copied = 0
    errors = 0

    print(f"Syncing reports to Obsidian Vault: {DEST_VAULT_ROOT} ...")

    # Iterate through immediate subdirectories of SOURCE_DIR
    try:
        subdirs = [d for d in os.listdir(SOURCE_DIR) if os.path.isdir(os.path.join(SOURCE_DIR, d))]
    except OSError as e:
        print(f"Error accessing source directory: {e}")
        return

    for subdir in subdirs:
        source_subdir_path = os.path.join(SOURCE_DIR, subdir)
        dest_subdir_path = None
        
        # Check for Daily Report pattern (YYYYMMDD)
        if re.match(r"^\d{8}$", subdir):
            dest_subdir_path = os.path.join(DEST_VAULT_ROOT, "daily", subdir)
        
        # Check for Deep Dive folder
        elif subdir == "deepdive":
            dest_subdir_path = os.path.join(DEST_VAULT_ROOT, "deepdive")
            
        # Skip other folders
        else:
            continue

        # If a valid destination is determined, sync the files
        if dest_subdir_path:
            if not os.path.exists(dest_subdir_path):
                try:
                    os.makedirs(dest_subdir_path)
                    print(f"  [+] Created folder: {dest_subdir_path}")
                except OSError as e:
                    print(f"  [!] Error creating folder {dest_subdir_path}: {e}")
                    continue

            # Sync .md files in this subdirectory
            for filename in os.listdir(source_subdir_path):
                if filename.endswith(".md"):
                    source_file = os.path.join(source_subdir_path, filename)
                    dest_file = os.path.join(dest_subdir_path, filename)
                    
                    try:
                        should_copy = False
                        if not os.path.exists(dest_file):
                            should_copy = True
                        else:
                            # Compare modification times
                            if os.path.getmtime(source_file) > os.path.getmtime(dest_file):
                                should_copy = True
                        
                        if should_copy:
                            shutil.copy2(source_file, dest_file)
                            # Display relative path for clarity
                            rel_dest = os.path.relpath(dest_file, DEST_VAULT_ROOT)
                            print(f"  [+] Synced: {rel_dest}")
                            files_copied += 1
                    except Exception as e:
                        print(f"  [!] Error syncing {filename}: {e}")
                        errors += 1

    if files_copied == 0:
        print("Everything is up-to-date.")
    else:
        print(f"Sync complete. {files_copied} files copied.")

if __name__ == "__main__":
    sync_reports()
