from statistics import pstdev
from backend.mac_api.modules.analytics import player_data, jump_data, gps_data, chart_statistics

def daily(records):
    return chart_statistics.daily_statistics(records, lambda item: item.get('value'))

OPERATIONS = {'chart_statistics.daily': daily, 'population_deviation': pstdev}
OPERATIONS["player_data.group_measurements"] = player_data.group_measurements
OPERATIONS["player_data.metric_summary"] = player_data.metric_summary
OPERATIONS["player_data.latest_eva"] = player_data.latest_eva
OPERATIONS["player_data.eva_classification"] = player_data.eva_classification
OPERATIONS["jump_data.average"] = jump_data.average
OPERATIONS["jump_data.metric_summary"] = jump_data.metric_summary
OPERATIONS["jump_data.build_jump_comparison"] = jump_data.build_jump_comparison
OPERATIONS["gps_data.average"] = gps_data.average
OPERATIONS["gps_data.opponents_by_date"] = gps_data.opponents_by_date
