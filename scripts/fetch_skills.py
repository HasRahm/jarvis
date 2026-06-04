import os
import urllib.request
import zipfile
import shutil
import tempfile

def fetch_skills():
    zip_url = "https://github.com/alirezarezvani/claude-skills/archive/refs/heads/main.zip"
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_dir = os.path.join(project_root, "skills")
    
    print(f"Downloading claude-skills repository from {zip_url}...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        zip_path = os.path.join(temp_dir, "claude-skills.zip")
        try:
            # Download the zip file
            urllib.request.urlretrieve(zip_url, zip_path)
            print("Download completed successfully! Extracting repository...")
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            
            # The zip extracts into a folder named "claude-skills-main"
            extracted_folder = os.path.join(temp_dir, "claude-skills-main")
            
            # Clear target directory if it exists
            if os.path.exists(target_dir):
                try:
                    shutil.rmtree(target_dir)
                except Exception as e:
                    print(f"Warning: could not fully clean {target_dir}: {e}")
            os.makedirs(target_dir, exist_ok=True)
            
            # We recursively find all SKILL.md files
            count = 0
            for root, dirs, files in os.walk(extracted_folder):
                for file in files:
                    if file.lower() == "skill.md":
                        skill_file_path = os.path.join(root, file)
                        # Root contains the skill directory
                        skill_dir = root
                        # The grandparent contains the domain directory
                        domain_dir = os.path.dirname(skill_dir)
                        
                        domain_name = os.path.basename(domain_dir)
                        skill_name = os.path.basename(skill_dir)
                        
                        # Avoid copying the top-level repo itself if there's any SKILL.md in root
                        if domain_name == "claude-skills-main" or skill_name == "claude-skills-main":
                            domain_name = "general"
                        
                        dest_skill_dir = os.path.join(target_dir, domain_name, skill_name)
                        os.makedirs(dest_skill_dir, exist_ok=True)
                        
                        # Copy all files in the skill directory recursively (markdown and python scripts)
                        for s_root, s_dirs, s_files in os.walk(skill_dir):
                            for s_file in s_files:
                                if s_file.endswith(".md") or s_file.endswith(".py") or s_file.endswith(".json"):
                                    s_file_path = os.path.join(s_root, s_file)
                                    rel_path = os.path.relpath(s_file_path, skill_dir)
                                    dest_file_path = os.path.join(dest_skill_dir, rel_path)
                                    os.makedirs(os.path.dirname(dest_file_path), exist_ok=True)
                                    shutil.copy2(s_file_path, dest_file_path)
                                    count += 1
            
            print(f"Successfully imported {count} files from matched skills into {target_dir}!")
            
        except Exception as e:
            print(f"Failed to fetch or extract skills: {e}")

if __name__ == "__main__":
    fetch_skills()
