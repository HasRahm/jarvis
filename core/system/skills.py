import sys
from core.trace import trace as _jtrace
import os
import re
import json
import logging
from typing import List, Dict, Optional
from core.system.plugin_loader import plugin_loader

logger = logging.getLogger(__name__)

STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "to", "for", "in", "on", "at", "by", "from",
    "with", "about", "against", "between", "into", "through", "during", "before",
    "after", "above", "below", "to", "of", "up", "down", "off", "over", "under",
    "again", "further", "then", "once", "here", "there", "when", "where", "why",
    "how", "all", "any", "both", "each", "few", "more", "most", "other", "some",
    "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    "s", "t", "can", "will", "just", "should", "now", "use", "using", "how", "to",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "having",
    "do", "does", "did", "doing", "i", "me", "my", "myself", "we", "our", "ours",
    "ourselves", "you", "your", "yours", "yourself", "yourselves", "he", "him",
    "his", "himself", "she", "her", "hers", "herself", "it", "its", "itself",
    "they", "them", "their", "theirs", "themselves", "what", "which", "who", "whom",
    "this", "that", "these", "those", "am"
}

class SkillsEngine:
    """Manages parsing, indexing, and matching modular developer skills for Jarvis."""

    def __init__(self, skills_dir: Optional[str] = None):
        if skills_dir is None:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            skills_dir = os.path.join(project_root, "skills")
        self.skills_dir = skills_dir
        self.skills: List[Dict] = []
        self._load_skills()

    def _load_skills(self):
        """Recursively scan skills directory and parse all SKILL.md files.
        
        Uses a JSON mtime cache to skip reparsing unchanged files. On a warm
        start with 767 skills and no changes, this drops from ~500-2000ms to ~10ms.
        """
        _jtrace(f"[TRACE] core.system.skills.SkillsEngine._load_skills: enter")
        self.skills = []
        if not os.path.exists(self.skills_dir):
            logger.warning(f"Skills directory '{self.skills_dir}' does not exist.")
            return

        cache_path = os.path.join(self.skills_dir, ".skills_cache.json")
        cache = {}
        try:
            if os.path.exists(cache_path):
                with open(cache_path, "r", encoding="utf-8") as cf:
                    cache = json.load(cf)
        except Exception:
            _jtrace(f"[TRACE] core.system.skills.SkillsEngine._load_skills: except Exception")
            cache = {}

        cache_dirty = False
        _SKIP_DIRS = {".git", ".github", "node_modules", "venv", ".venv", "env", "__pycache__", "dist", "build", "target", "assets"}
        for root, dirs, files in os.walk(self.skills_dir):
            # Skip hidden/tool-converted dirs and heavy dependency black holes in-place
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in _SKIP_DIRS]
            for file in files:
                if file.lower() == "skill.md":
                    file_path = os.path.join(root, file)
                    try:
                        mtime = os.path.getmtime(file_path)
                    except OSError:
                        _jtrace(f"[TRACE] core.system.skills.SkillsEngine._load_skills: except OSError")
                        continue
                    
                    # Check cache: if mtime matches, use cached data (skip file I/O + parsing)
                    cached_entry = cache.get(file_path)
                    if cached_entry and cached_entry.get("mtime") == mtime:
                        # Reconstruct skill from cache (tokens stored as list, convert to set)
                        skill_data = {
                            "name": cached_entry["name"],
                            "description": cached_entry["description"],
                            "path": file_path,
                            "content": cached_entry.get("content", ""),
                            "tokens": set(cached_entry.get("tokens", []))
                        }
                        self.skills.append(skill_data)
                        continue
                    
                    # Cache miss — parse the file
                    skill_data = self._parse_skill_file(file_path)
                    if skill_data:
                        self.skills.append(skill_data)
                        # Update cache (tokens stored as list for JSON serialization)
                        cache[file_path] = {
                            "mtime": mtime,
                            "name": skill_data["name"],
                            "description": skill_data["description"],
                            "content": skill_data["content"],
                            "tokens": list(skill_data["tokens"])
                        }
                        cache_dirty = True
        
        # Load custom registered skills from plugins
        try:
            for skill_path in plugin_loader.skills:
                skill_data = self._parse_skill_file(skill_path)
                if skill_data:
                    self.skills.append(skill_data)
        except Exception as pe:
            _jtrace(f"[TRACE] core.system.skills.SkillsEngine._load_skills: except {str(pe)[:80]}")
            logger.warning(f"Failed loading plugin skills: {pe}")
        
        # Persist cache if anything changed
        if cache_dirty:
            try:
                with open(cache_path, "w", encoding="utf-8") as cf:
                    json.dump(cache, cf)
            except Exception as ce:
                _jtrace(f"[TRACE] core.system.skills.SkillsEngine._load_skills: except {str(ce)[:80]}")
                logger.warning(f"Could not write skills cache: {ce}")
        
        logger.info(f"SkillsEngine: Loaded {len(self.skills)} developer skills.")

    def _parse_skill_file(self, file_path: str) -> Optional[Dict]:
        """Parse frontmatter and markdown content from a SKILL.md file."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Separate YAML frontmatter and content
            yaml_pattern = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
            match = yaml_pattern.match(content)
            
            metadata = {}
            body_content = content
            
            if match:
                frontmatter_text = match.group(1)
                body_content = content[match.end():]
                # Simple parser for YAML key-values
                for line in frontmatter_text.split("\n"):
                    if ":" in line:
                        k, v = line.split(":", 1)
                        metadata[k.strip().lower()] = v.strip().strip('"').strip("'")
            
            # Extract basic info
            name = metadata.get("name")
            description = metadata.get("description")
            
            # Extract fallback from Markdown if YAML is incomplete
            if not name:
                # Find the first H1
                h1_match = re.search(r"^#\s+(.+)$", body_content, re.MULTILINE)
                if h1_match:
                    name = h1_match.group(1).strip()
                else:
                    # Fallback to parent directory name
                    name = os.path.basename(os.path.dirname(file_path)).replace("-", " ").replace("_", " ").title()
            
            if not description:
                # Extract first paragraph
                paragraphs = [p.strip() for p in body_content.split("\n\n") if p.strip()]
                for p in paragraphs:
                    if not p.startswith("#") and not p.startswith(">") and not p.startswith("-"):
                        description = p[:200] + "..." if len(p) > 200 else p
                        break
                if not description:
                    description = f"Specialized guidelines for {name} tasks."

            # Normalize name/description for search
            searchable_tokens = self._tokenize(f"{name} {description}")

            return {
                "name": name,
                "description": description,
                "path": file_path,
                "content": body_content.strip(),
                "tokens": searchable_tokens
            }
        except Exception as e:
            _jtrace(f"[TRACE] core.system.skills.SkillsEngine._parse_skill_file: except {str(e)[:80]}")
            logger.error(f"Failed to parse skill file '{file_path}': {e}")
            return None

    def _tokenize(self, text: str) -> set[str]:
        """Clean, lowercase, and tokenize text into alphanumeric words, filtering out stop words."""
        _jtrace(f"[TRACE] core.system.skills.SkillsEngine._tokenize: enter")
        words = re.findall(r"\b[a-zA-Z0-9_-]+\b", text.lower())
        return {w for w in words if w not in STOP_WORDS and len(w) > 1}

    def get_relevant_skills(self, task: str, limit: int = 3) -> List[Dict]:
        """Match task keywords against skills and return top matching skills."""
        _jtrace(f"[TRACE] core.system.skills.SkillsEngine.get_relevant_skills: enter")
        if not self.skills:
            self._load_skills()
            if not self.skills:
                return []

        task_tokens = self._tokenize(task)
        if not task_tokens:
            return []

        scored_skills = []
        for skill in self.skills:
            intersection = task_tokens.intersection(skill["tokens"])
            score = len(intersection)
            if score > 0:
                scored_skills.append((score, skill))

        # Sort by overlap score descending
        scored_skills.sort(key=lambda x: x[0], reverse=True)
        
        relevant = [skill for score, skill in scored_skills[:limit]]
        if relevant:
            logger.info(f"SkillsEngine: Matched {len(relevant)} skill(s) for task: '{task[:50]}...'")
        return relevant

    def get_skill_by_name(self, skill_name: str) -> Optional[Dict]:
        """Look up a parsed skill by exact name (case-insensitive), else None.

        Resolves skills anywhere under skills/ — including vendored clones in
        skills/external/ — because it searches the already-parsed index rather than
        guessing hardcoded paths."""
        _jtrace(f"[TRACE] core.system.skills.SkillsEngine.get_skill_by_name: enter")
        if not self.skills:
            self._load_skills()
        target = (skill_name or "").strip().lower()
        for skill in self.skills:
            if (skill.get("name") or "").strip().lower() == target:
                return skill
        return None

    def get_skill_content(self, skill_name: str) -> str:
        """Return the parsed SKILL.md body for a named skill (for SkillAgent personas)."""
        _jtrace(f"[TRACE] core.system.skills.SkillsEngine.get_skill_content: enter")
        skill = self.get_skill_by_name(skill_name)
        if skill and skill.get("content"):
            return skill["content"]
        # Fall back to the raw file read (handles names that differ from frontmatter).
        return self.load_skill_prompt(skill_name)

    def load_skill_prompt(self, skill_name: str) -> str:
        """Return the raw SKILL.md body content for a named skill (for use in run_skill)."""
        # 1. Prefer the parsed index — finds skills nested anywhere under skills/ (incl. external/).
        _jtrace(f"[TRACE] core.system.skills.SkillsEngine.load_skill_prompt: enter")
        skill = self.get_skill_by_name(skill_name)
        if skill and skill.get("path") and os.path.exists(skill["path"]):
            with open(skill["path"], "r", encoding="utf-8") as f:
                return f.read()
        # 2. Fall back to the legacy hardcoded layout.
        candidates = [
            os.path.join(self.skills_dir, "skills", skill_name, "SKILL.md"),
            os.path.join(self.skills_dir, skill_name, "SKILL.md"),
        ]
        for path in candidates:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
        raise FileNotFoundError(
            f"Skill '{skill_name}' not found in index or {candidates}. "
            f"Available skills can be listed from the skills/ directory."
        )

    def get_skills_prompt_addition(self, task: str) -> str:
        """Generate a formatted markdown addition to append to the system prompt containing relevant skill rules."""
        _jtrace(f"[TRACE] core.system.skills.SkillsEngine.get_skills_prompt_addition: enter")
        relevant = self.get_relevant_skills(task)
        if not relevant:
            return ""

        prompt_add = "\n\n--- DYNAMIC SKILLS & DOMAIN EXPERTISE ENABLED ---\n"
        prompt_add += "You have been matched with the following specialized skills/guidelines for this task. "
        prompt_add += "Follow these instructions meticulously to ensure success:\n\n"

        for skill in relevant:
            prompt_add += f"### SKILL: {skill['name']}\n"
            prompt_add += f"*Description: {skill['description']}*\n\n"
            prompt_add += f"{skill['content']}\n\n"
            
        prompt_add += "------------------------------------------------\n\n"
        return prompt_add
