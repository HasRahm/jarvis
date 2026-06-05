import os
import re
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
        """Recursively scan skills directory and parse all SKILL.md files."""
        self.skills = []
        if not os.path.exists(self.skills_dir):
            logger.warning(f"Skills directory '{self.skills_dir}' does not exist.")
            return

        for root, dirs, files in os.walk(self.skills_dir):
            for file in files:
                if file.lower() == "skill.md":
                    file_path = os.path.join(root, file)
                    skill_data = self._parse_skill_file(file_path)
                    if skill_data:
                        self.skills.append(skill_data)
        
        # Load custom registered skills from plugins
        try:
            for skill_path in plugin_loader.skills:
                skill_data = self._parse_skill_file(skill_path)
                if skill_data:
                    self.skills.append(skill_data)
        except Exception as pe:
            logger.warning(f"Failed loading plugin skills: {pe}")
        
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
            logger.error(f"Failed to parse skill file '{file_path}': {e}")
            return None

    def _tokenize(self, text: str) -> set[str]:
        """Clean, lowercase, and tokenize text into alphanumeric words, filtering out stop words."""
        words = re.findall(r"\b[a-zA-Z0-9_-]+\b", text.lower())
        return {w for w in words if w not in STOP_WORDS and len(w) > 1}

    def get_relevant_skills(self, task: str, limit: int = 3) -> List[Dict]:
        """Match task keywords against skills and return top matching skills."""
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

    def get_skills_prompt_addition(self, task: str) -> str:
        """Generate a formatted markdown addition to append to the system prompt containing relevant skill rules."""
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
