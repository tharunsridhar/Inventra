from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    """DRF's PageNumberPagination ignores ?page_size=N unless this is set -
    without it, every list endpoint silently returns exactly PAGE_SIZE (20)
    regardless of what a client asks for. The frontend relies on requesting
    larger pages (page_size=100) to bulk-load reference data like products/
    suppliers for dropdowns."""

    page_size_query_param = "page_size"
    max_page_size = 200
