"""Tests for CAMP / PLY join code normalization and campaign lookup."""

import unittest
from unittest.mock import MagicMock, patch

from sqlalchemy.exc import IntegrityError

from app import app
from app.models import Campaign
from app.services import join_codes as jc


class JoinCodesTests(unittest.TestCase):
    def test_normalize_folds_homoglyphs_in_camp_payload(self):
        self.assertEqual(
            jc.normalize_code("CAMP-ABCD-EFGH-IJKL"),
            "CAMP-ABCD-EFGH-1JK1",
        )

    def test_normalize_ply_payload(self):
        self.assertEqual(
            jc.normalize_code("PLY-ABCD-EFGH-ILIL"),
            "PLY-ABCD-EFGH-1111",
        )

    def test_find_campaign_by_join_code_requires_camp_prefix(self):
        with app.app_context():
            with patch.object(Campaign, "query") as mock_query:
                self.assertIsNone(jc.find_campaign_by_join_code("PLY-ABCD-EFGH-JKLM"))
                mock_query.filter_by.assert_not_called()

    def test_find_campaign_by_join_code_queries_when_camp_prefixed(self):
        with app.app_context():
            sentinel = object()
            with patch.object(Campaign, "query") as mock_query:
                mock_query.filter_by.return_value.first.return_value = sentinel
                r = jc.find_campaign_by_join_code("CAMP-ABCD-EFGH-JKLM")
                self.assertIs(r, sentinel)
                mock_query.filter_by.assert_called_once_with(
                    join_code="CAMP-ABCD-EFGH-JKLM"
                )

    @patch("app.services.join_codes.generate_raw_code", return_value="CAMP-AAAA-AAAA-AAAA")
    @patch("app.services.join_codes.db.session")
    def test_ensure_campaign_join_code_reclears_pollution_after_integrity_rollback(
        self, mock_session, _mock_gen
    ):
        """Rollback after IntegrityError must not leave a path that returns TEST- etc."""

        def make_fresh(join_code):
            m = MagicMock()
            m.id = 7
            m.gm_profile_id = 9
            m.join_code = join_code
            return m

        f1, f2 = make_fresh("TEST-BAD"), make_fresh("TEST-BAD")
        filt = MagicMock()
        filt.first.side_effect = [f1, f2]

        flush_calls = [0]

        def flush_impl():
            flush_calls[0] += 1
            if flush_calls[0] == 2:
                raise IntegrityError(None, None, None)

        mock_session.flush.side_effect = flush_impl

        campaign = MagicMock()
        campaign.id = 7
        campaign.gm_profile_id = 9

        with app.app_context():
            with patch.object(Campaign, "query") as qm:
                qm.filter_by.return_value = filt
                out = jc.ensure_campaign_join_code_for_campaign(campaign)

        self.assertEqual(out, "CAMP-AAAA-AAAA-AAAA")
        mock_session.rollback.assert_called_once()


if __name__ == "__main__":
    unittest.main()
