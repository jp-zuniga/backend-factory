from pydantic import BaseModel, ConfigDict

########################################################################################


class DTO(BaseModel):
    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        field_title_generator=(lambda s, _: s.lower()),
        from_attributes=True,
        frozen=True,
        str_strip_whitespace=True,
    )


########################################################################################


class PermissiveDTO(DTO):
    model_config = ConfigDict(extra="ignore")
