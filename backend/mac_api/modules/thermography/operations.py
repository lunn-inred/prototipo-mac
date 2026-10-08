"""Stateless processing API used by web and desktop clients."""
from typing import Any, Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from backend.mac_api.core.wire import encode, decode
from backend.mac_api.modules.thermography import thermal_analysis as thermal

router = APIRouter()
OPERATIONS = {name: getattr(thermal, name) for name in (
    'annotate_boxes', 'compare_hot_masks', 'count_hot_pixels', 'detect_colorbar_box',
    'detect_leg_boxes', 'hot_pixels_overlay', 'segmentation_overlay', 'segment_leg_mask',
    'temperature_matrix', 'leg_part_metrics', 'scale_percentage_from_temperature',
    'temperature_from_scale_percentage', 'segmented_image', 'timeline_view_at_threshold',
    'summarize_pair',
)}

class ProcessingInput(BaseModel):
    args: list[Any] = Field(default_factory=list)
    kwargs: dict[str, Any] = Field(default_factory=dict)

class ProcessingOutput(BaseModel):
    result: Any


class ImagePayload(BaseModel):
    type: Literal['image'] = 'image'
    png: str


class ArrayPayload(BaseModel):
    type: Literal['array'] = 'array'
    dtype: Literal['bool', 'uint8', 'int8', 'float32', 'float64', 'int64']
    shape: list[int] = Field(min_length=1, max_length=3)
    data: str


class BoundingBox(BaseModel):
    left: int = Field(ge=0)
    top: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class SegmentationInput(BaseModel):
    image: ImagePayload
    view: Literal['front', 'back']
    minimum_temperature: float = Field(allow_inf_nan=False)
    maximum_temperature: float = Field(allow_inf_nan=False)
    threshold: float = Field(allow_inf_nan=False)
    manual_boxes: dict[Literal['right', 'left'], BoundingBox] | None = None
    colorbar_box: BoundingBox | None = None
    seeds: dict[Literal['right', 'left'], ArrayPayload] | None = None


class LegMetric(BaseModel):
    hot_pixels: int = Field(ge=0)
    total_pixels: int = Field(gt=0)
    hot_percentage: float = Field(ge=0, le=100)
    threshold: float


class SegmentationOutput(BaseModel):
    view: Literal['front', 'back']
    boxes: dict[str, BoundingBox]
    automatic_boxes: dict[str, BoundingBox]
    masks: dict[str, ArrayPayload]
    metrics: dict[str, LegMetric]
    overlay: ImagePayload
    hot_overlay: ImagePayload
    colorbar_box: BoundingBox
    automatic_colorbar_box: BoundingBox
    colorbar_confidence: float
    temperatures: ArrayPayload
    threshold: float


@router.post('/thermography/segment', response_model=SegmentationOutput, tags=['Processamento térmico'])
async def segment(payload: SegmentationInput):
    values = decode(payload.model_dump())
    result = await run_in_threadpool(thermal.segmented_image, **values)
    return encode(result)

def execute(operation, payload):
    try:
        return {'result': encode(OPERATIONS[operation](*decode(payload.args), **decode(payload.kwargs)))}
    except (TypeError, KeyError) as error:
        raise ValueError('Parâmetros de processamento inválidos.') from error

@router.post('/thermography/operations/{operation}', response_model=ProcessingOutput, tags=['Processamento térmico'])
async def process(operation: str, payload: ProcessingInput):
    if operation not in OPERATIONS:
        raise HTTPException(status_code=404, detail='Operação térmica desconhecida.')
    return await run_in_threadpool(execute, operation, payload)
