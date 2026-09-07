from enum import StrEnum


class SortField(StrEnum):
    METASCORE = "metascore"
    USERSCORE = "userscore"
    TITLE = "title"
    CREATED_AT = "created_at"


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"
