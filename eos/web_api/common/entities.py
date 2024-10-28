from pydantic import BaseModel


class TaskTypesResponse(BaseModel):
    task_types: list[str] | str


class ExperimentTypes(BaseModel):
    experiment_types: list[str] | str


class ExperimentTypesResponse(BaseModel):
    experiment_types: list[str]


class ExperimentDynamicParamsTemplateResponse(BaseModel):
    dynamic_params_template: str


class LabTypes(BaseModel):
    lab_types: list[str] | str
