import unittest

from common.sample_matching import match_condition, match_tissue, tissue_query_terms


class SampleMatchingTests(unittest.TestCase):
    def test_anatomical_parent_relationships_and_unknown_names(self):
        cases = [("brain", "cerebral cortex", "match"), ("brain", "hippocampus", "match"),
                 ("brain", "renal cortex", "mismatch"), ("cerebral cortex", "brain", "unknown"),
                 ("brain", "unmapped tissue label", "unknown"), ("leaf", "leaves", "match"),
                 ("brain", "liver", "mismatch"), ("brain", "brain and liver", "unknown")]
        for query, observed, expected in cases:
            with self.subTest(query=query, observed=observed):
                self.assertEqual(match_tissue({"tissue_type": observed}, query)[0], expected)
        self.assertIn("cerebral cortex", tissue_query_terms("brain"))
        self.assertNotIn("brain", tissue_query_terms("cerebral cortex"))

    def test_structured_tissue_overrides_narrative_and_preserves_conflicts(self):
        metadata = {"tissue_type": "liver", "sample_description": "Brain and liver comparison"}
        self.assertEqual(match_tissue(metadata, "brain")[0], "mismatch")
        metadata["attribute:tissue"] = "brain"
        self.assertEqual(match_tissue(metadata, "brain")[0], "unknown")
        self.assertEqual(match_tissue({"sample_description": "not brain tissue"}, "brain")[0], "unknown")
        self.assertEqual(match_tissue({"sample_title": "human_liver"}, "liver")[0], "match")

    def test_comparison_text_never_establishes_healthy_specimen(self):
        for value in ("Tumor sample compared with healthy controls", "healthy versus tumor samples",
                      "normal and tumor tissue comparison", "not healthy", "disease status unknown"):
            with self.subTest(value=value):
                self.assertEqual(match_condition({"sample_description": value}, "healthy")[0], "unknown")

    def test_structured_health_and_disease_status(self):
        cases = [({"attribute:disease": "normal"}, "healthy", "match"),
                 ({"attribute:health_status": "healthy"}, "normal", "match"),
                 ({"attribute:disease": "hepatocellular carcinoma"}, "healthy", "mismatch"),
                 ({"attribute:disease": "healthy"}, "cancer", "mismatch"),
                 ({"attribute:disease": "not healthy"}, "healthy", "mismatch"),
                 ({"attribute:disease": "unknown"}, "healthy", "unknown"),
                 ({"attribute:treatment": "drought"}, "drought", "match"),
                 ({"attribute:treatment": "healthy conditioned medium"}, "healthy", "unknown"),
                 ({"attribute:disease": "normal", "attribute:diagnosis": "tumor"}, "healthy", "unknown")]
        for metadata, query, expected in cases:
            with self.subTest(metadata=metadata, query=query):
                self.assertEqual(match_condition(metadata, query)[0], expected)

    def test_specimen_attributes_take_precedence_over_comparisons(self):
        metadata = {"attribute:disease": "tumor", "sample_description": "compared with healthy controls"}
        status, fields, _ = match_condition(metadata, "healthy")
        self.assertEqual(status, "mismatch")
        self.assertEqual(fields, ["attribute:disease"])
