"""What kind of source a chunk is, and where it sits in the source order.

  verified fix  >  course material (Dr. Inglis's notes + his dissection guides, the SAME tier)  >  OpenStax  >  trusted web

chunk["source_type"]: notes | dissection_guide | open_text | web.  The "kind" used in citations and prompts:
  notes -> "notes", dissection_guide -> "guide", open_text -> "openstax", web -> "web".
"""
COURSE_TYPES = ("notes", "dissection_guide")
KIND = {"notes": "notes", "dissection_guide": "guide", "open_text": "openstax", "web": "web"}
PROMPT_KIND = {"notes": "course_notes", "dissection_guide": "dissection_guide", "open_text": "openstax", "web": "web"}


def kind_of(chunk):
    return KIND.get(chunk.get("source_type"), "notes")


def is_course(chunk):
    """Dr. Inglis's own material (notes or dissection guide): the highest tier after a verified fix."""
    return chunk.get("source_type") in COURSE_TYPES


def tier_of(chunks):
    """The highest tier among the chunks an answer used: 'course' | 'openstax' | 'web' | 'none'."""
    types = {c.get("source_type") for c in chunks}
    if types & set(COURSE_TYPES):
        return "course"
    if "open_text" in types:
        return "openstax"
    if "web" in types:
        return "web"
    return "none"
