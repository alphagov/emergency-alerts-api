from app.models import FeatureToggle


def dao_get_feature_toggles():
    return FeatureToggle.query.all()


def dao_get_feature_toggle_by_name(feature_toggle_name):
    return FeatureToggle.query.filter_by(name=feature_toggle_name).first()
