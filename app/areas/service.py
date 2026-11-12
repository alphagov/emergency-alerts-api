from app.areas.resolvers import AreaResolverRegistry


class AreaService:
    @staticmethod
    def get_areas(area_ids):
        """
        Resolve a collection of area identifiers into
        serialized area responses.
        """

        # Preserve order while removing duplicates
        unique_ids = list(dict.fromkeys(area_ids))

        return AreaResolverRegistry.resolve_all(unique_ids)
