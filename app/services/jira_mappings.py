# Mappings
BASE_ISSUE_MAP = {
    "issuetype" : ("issuetype", None),
    "summary": ("summary", None),
    "description": ("description", None),
    "priority": ("priority", None),
    "status": ("status", "name"),
    "created": ("created", None),
    "updated": ("updated", None),
    "resolution": ("resolution", None),
    "resolutiondate": ("resolutiondate", None),
    "assignee": ("assignee", "emailAddress"),
    "reporter": ("reporter", None),
    "duedate": ("duedate", None),
    "team":("project", None),
    "release" : ("fixVersions", None),
    "labels" : ("labels", None),
    "notes": ("customfield_10602", None),
    "components": ("components", None),
    "links" : ("issuelinks", None),
}

STORY_ISSUE_MAP = {
    "story_points" : ("customfield_10106", None),
    "parent" : ("customfield_10100", None),
    "blocked" : ("customfield_10900", None),
    "targetstart" : ("customfield_10202", None),
    "targetend" : ("customfield_10203", None),
    "applicationname" : ("customfield_11700", None),
    "acceptancecriteria" : ("customfield_10601", None),
    
}

DEFECT_ISSUE_MAP = {
    "storypoints" : ("customfield_10016", None),
    "epic" : ("epic", "Name"),

}

ISSUE_TYPE_MAPS = {
    "Story" : STORY_ISSUE_MAP,
    "Defect" : DEFECT_ISSUE_MAP,
}

def merge_maps(base: dict, extra: dict | None = None) -> dict:
    return {**base, **(extra or {})}

def get_map(issue_type: str | None) -> dict:
    return merge_maps(BASE_ISSUE_MAP, ISSUE_TYPE_MAPS.get(issue_type))
    