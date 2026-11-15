from src.services import sample_service as service
from src.services.measurement_service import LEGACY_CODES


def _out(item):
    return {
        'id': item.id, 'code': item.code, 'name': item.name, 'family': item.family,
        'absorption': item.absorption, 'impact': item.impact, 'carbon': item.carbon,
        'price': item.price, 'thickness': item.thickness, 'batch': item.batch,
        'measurements': {m.metric_code: m.value for m in item.measurement_rows
                         if m.metric_code not in LEGACY_CODES},
    }


def index(db):
    return [_out(s) for s in service.list_samples(db)]


def create(db, data):
    return _out(service.create_sample(db, data))


def update(db, id, data):
    return _out(service.update_sample(db, id, data))
