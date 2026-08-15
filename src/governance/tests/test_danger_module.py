"""Standalone tests for the public danger heuristic module (DEBT-0002).

The heuristic moved out of src.main (private _is_dangerous) into src.danger
(public is_dangerous). These tests pin the PUBLIC API and verify behavior
is identical to the old private function: importable standalone, 3-layer
defense (boundary prefix, segment fallback, query-string strip), and the
DANGEROUS_METHODS gate with case-insensitivity.
"""

from src.danger import DANGEROUS_PREFIXES, DANGEROUS_METHODS, is_dangerous


class TestDangerModulePublicAPI:
    def test_module_importable_without_main(self):
        import src.danger as d
        assert d.__all__ == ["DANGEROUS_PREFIXES", "DANGEROUS_METHODS", "is_dangerous"]

    def test_prefixes_exported(self):
        assert "/api/delete" in DANGEROUS_PREFIXES
        assert "/api/admin" in DANGEROUS_PREFIXES
        assert len(DANGEROUS_PREFIXES) == 4

    def test_methods_exported(self):
        assert "DELETE" in DANGEROUS_METHODS
        assert "POST" in DANGEROUS_METHODS
        assert len(DANGEROUS_METHODS) == 4


class TestDangerHeuristicBehavior:
    def test_non_dangerous_method_passes(self):
        assert is_dangerous("/api/delete", "GET") is False

    def test_exact_prefix_hits(self):
        assert is_dangerous("/api/delete", "POST") is True

    def test_prefix_with_subpath_hits(self):
        assert is_dangerous("/api/delete/records/42", "DELETE") is True

    def test_boundary_prevents_prefix_squatting(self):
        assert is_dangerous("/api/delete-evil", "POST") is False

    def test_segment_fallback_hits_variant(self):
        assert is_dangerous("/api/v1/delete", "DELETE") is True

    def test_query_string_stripped(self):
        assert is_dangerous("/api/config?secret=1", "PUT") is True

    def test_method_case_insensitive(self):
        assert is_dangerous("/api/admin", "post") is True

    def test_safe_public_path_clean(self):
        assert is_dangerous("/api/chat", "POST") is False

    def test_admin_prefix_hits(self):
        assert is_dangerous("/api/admin/users", "PATCH") is True
