from src.services import base_metric_service as service
from src.services import measurement_service as measurements
from src.services import derivation_service as derived


def list_metrics(db, study_id):
    return service.list_base_metrics(db, study_id)


def create_metric(db, data):
    return service.create_base_metric(db, data)


def update_metric(db, id, data):
    return service.update_base_metric(db, id, data)


def list_measurements(db, study_id):
    return measurements.list_measurements(db, study_id)


def upsert_measurement(db, sample_id, metric_code, value):
    # The service commits the value and incrementally recomputes only this
    # sample's downstream derived chain across all studies.
    measurements.upsert_measurement(db, sample_id, metric_code, value)


def preview(db, study_id):
    return derived.preview_study(db, study_id)
