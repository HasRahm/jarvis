import pytest
import os
from core.system.skills import SkillsEngine

def test_skills_engine_loads_skills():
    engine = SkillsEngine()
    assert len(engine.skills) > 0, "No skills loaded from skills folder!"

def test_skills_engine_matches_backend_task():
    engine = SkillsEngine()
    relevant = engine.get_relevant_skills("design REST APIs and optimize database migrations")
    
    assert len(relevant) > 0
    # The senior-backend skill should be matched
    matched_names = [skill["name"].lower() for skill in relevant]
    assert any("backend" in name or "senior-backend" in name for name in matched_names)

def test_skills_engine_matches_frontend_task():
    engine = SkillsEngine()
    relevant = engine.get_relevant_skills("build senior-frontend React component with beautiful styling")
    
    assert len(relevant) > 0
    matched_names = [skill["name"].lower() for skill in relevant]
    assert any("frontend" in name or "senior-frontend" in name for name in matched_names)

def test_skills_engine_matches_qa_task():
    engine = SkillsEngine()
    relevant = engine.get_relevant_skills("verify API test suite and write Playwright tests")
    
    assert len(relevant) > 0
    matched_names = [skill["name"].lower() for skill in relevant]
    assert any("qa" in name or "test" in name or "browser" in name for name in matched_names)

def test_skills_prompt_addition():
    engine = SkillsEngine()
    addition = engine.get_skills_prompt_addition("optimize database queries for PostgreSQL")
    
    assert "DYNAMIC SKILLS & DOMAIN EXPERTISE ENABLED" in addition
    assert "senior-backend" in addition.lower() or "database" in addition.lower()
