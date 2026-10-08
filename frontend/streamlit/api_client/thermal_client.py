"""HTTP adapters. Image analysis is exclusively executed by FastAPI."""
from frontend.streamlit.api_client.service_gateway import _request
from frontend.streamlit.api_client.wire import encode, decode

LEG_PARTS = ('coxa', 'joelho', 'canela', 'pe')
DEFAULT_PART_CUTS = (45, 57, 88)

def _adapter(operation):
    def call(*args, **kwargs):
        payload = {'args': encode(args), 'kwargs': encode(kwargs)}
        response = _request('POST', f'/api/v1/thermography/operations/{operation}', json=payload)
        return decode(response['result'])
    call.__name__ = operation
    return call

for _name in (
    'annotate_boxes', 'compare_hot_masks', 'count_hot_pixels', 'detect_colorbar_box',
    'detect_leg_boxes', 'hot_pixels_overlay', 'segmentation_overlay', 'segment_leg_mask',
    'temperature_matrix', 'leg_part_metrics', 'scale_percentage_from_temperature',
    'temperature_from_scale_percentage', 'segmented_image', 'timeline_view_at_threshold',
    'summarize_pair',
):
    globals()[_name] = _adapter(_name)


def segmented_image(image, view, minimum_temperature, maximum_temperature, threshold,
                    manual_boxes=None, colorbar_box=None, seeds=None):
    payload = encode(dict(image=image, view=view, minimum_temperature=minimum_temperature,
                          maximum_temperature=maximum_temperature, threshold=threshold,
                          manual_boxes=manual_boxes, colorbar_box=colorbar_box, seeds=seeds))
    return decode(_request('POST', '/api/v1/thermography/segment', json=payload))
