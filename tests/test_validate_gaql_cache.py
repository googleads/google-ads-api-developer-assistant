# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unit tests for local SHA-256 response caching in validate_gaql.py."""

import hashlib
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = PROJECT_ROOT / "plugins" / "google-ads-api-developer-assistant"
VALIDATE_GAQL_DIR = PLUGIN_ROOT / "skills" / "validate-gaql" / "scripts"

if str(VALIDATE_GAQL_DIR) not in sys.path:
    sys.path.insert(0, str(VALIDATE_GAQL_DIR))

import validate_gaql as vg  # noqa: E402


class TestValidateGaqlCache:
    """Tests for SHA-256 keyed GAQL validation response caching (hits, misses, invalidation)."""

    def test_compute_gaql_cache_key_deterministic_and_normalized(self):
        """SHA-256 cache key is deterministic and normalizes whitespace and API version prefix."""
        query = "SELECT campaign.id, campaign.name FROM campaign"
        key1 = vg.compute_gaql_cache_key(query, "v25")
        key2 = vg.compute_gaql_cache_key(f"  {query}\n  ", "25")
        key3 = vg.compute_gaql_cache_key(query, "V25")

        expected = hashlib.sha256(f"{query}|v25".encode("utf-8")).hexdigest()
        assert key1 == expected
        assert key1 == key2
        assert key1 == key3
        assert len(key1) == 64

        # Different query or different API version produces a distinct SHA-256 hash
        key_diff_query = vg.compute_gaql_cache_key("SELECT campaign.id FROM campaign", "v25")
        key_diff_ver = vg.compute_gaql_cache_key(query, "v24")
        assert key1 != key_diff_query
        assert key1 != key_diff_ver

    def test_cache_miss_then_hit_skips_api_dry_run(self, tmp_path, capsys):
        """First validation is a cache miss (calls API); second identical call is a cache hit (skips API)."""
        cache_file = str(tmp_path / "gaql_cache.json")
        mock_client = MagicMock()
        mock_service = MagicMock()
        mock_client.get_service.return_value = mock_service
        query = "SELECT campaign.id, campaign.name FROM campaign"

        # 1. Cache miss: API dry-run should execute and populate the cache
        assert vg.get_cached_validation(query, "v25", cache_path=cache_file) is None
        vg.validate_gaql(
            customer_id="123-456-7890",
            api_version="v25",
            query=query,
            client=mock_client,
            use_cache=True,
            cache_path=cache_file,
        )
        assert mock_service.search.call_count == 1
        out1 = capsys.readouterr().out
        assert "SUCCESS: GAQL query is structurally valid." in out1
        assert "(cached)" not in out1

        # Verify cache entry now exists on disk and in memory
        cached = vg.get_cached_validation(query, "v25", cache_path=cache_file)
        assert cached is not None
        assert cached["valid"] is True
        assert cached["key"] == vg.compute_gaql_cache_key(query, "v25")
        assert os.path.isfile(cache_file)

        # 2. Cache hit: second call with same (query, api_version) must NOT invoke ga_service.search
        vg.validate_gaql(
            customer_id="123-456-7890",
            api_version="v25",
            query=query,
            client=mock_client,
            use_cache=True,
            cache_path=cache_file,
        )
        assert mock_service.search.call_count == 1  # Unchanged!
        out2 = capsys.readouterr().out
        assert "SUCCESS: GAQL query is structurally valid. (cached)" in out2

    def test_cache_miss_on_different_query_or_api_version(self, tmp_path):
        """Changing either the query or the API version results in a cache miss."""
        cache_file = str(tmp_path / "gaql_cache.json")
        mock_client = MagicMock()
        mock_service = MagicMock()
        mock_client.get_service.return_value = mock_service

        q1 = "SELECT campaign.id FROM campaign"
        q2 = "SELECT campaign.id, campaign.name FROM campaign"

        vg.validate_gaql("1234567890", "v25", q1, client=mock_client, cache_path=cache_file)
        assert mock_service.search.call_count == 1

        # Different query -> cache miss -> calls API (count = 2)
        vg.validate_gaql("1234567890", "v25", q2, client=mock_client, cache_path=cache_file)
        assert mock_service.search.call_count == 2

        # Same query q1, but different api_version (v24) -> cache miss -> calls API (count = 3)
        vg.validate_gaql("1234567890", "v24", q1, client=mock_client, cache_path=cache_file)
        assert mock_service.search.call_count == 3

        # Repeat (q1, v24) -> cache hit -> count remains 3
        vg.validate_gaql("1234567890", "v24", q1, client=mock_client, cache_path=cache_file)
        assert mock_service.search.call_count == 3

    def test_disk_cache_persistence_across_memory_reset(self, tmp_path):
        """Cached results persist on disk and reload when the in-memory cache is cleared."""
        cache_file = str(tmp_path / "gaql_cache.json")
        query = "SELECT customer.id FROM customer"
        vg.set_cached_validation(query, "v25", valid=True, cache_path=cache_file)

        # Simulate a fresh process by clearing the in-memory dictionary
        vg._GAQL_MEMORY_CACHE.clear()

        loaded = vg.get_cached_validation(query, "v25", cache_path=cache_file)
        assert loaded is not None
        assert loaded["query"] == query
        assert loaded["api_version"] == "v25"
        assert loaded["valid"] is True

    def test_cache_invalidation_single_version_and_all(self, tmp_path):
        """invalidate_gaql_cache supports single-entry, per-version, and full cache invalidation."""
        cache_file = str(tmp_path / "gaql_cache.json")
        q1 = "SELECT campaign.id FROM campaign"
        q2 = "SELECT ad_group.id FROM ad_group"
        q3 = "SELECT customer.id FROM customer"

        vg.set_cached_validation(q1, "v25", cache_path=cache_file)
        vg.set_cached_validation(q2, "v25", cache_path=cache_file)
        vg.set_cached_validation(q3, "v24", cache_path=cache_file)

        # 1. Invalidate a single (query, api_version) entry
        removed_single = vg.invalidate_gaql_cache(query=q1, api_version="v25", cache_path=cache_file)
        assert removed_single == 1
        assert vg.get_cached_validation(q1, "v25", cache_path=cache_file) is None
        assert vg.get_cached_validation(q2, "v25", cache_path=cache_file) is not None
        assert vg.get_cached_validation(q3, "v24", cache_path=cache_file) is not None

        # Invalidating a non-existent entry returns 0
        assert vg.invalidate_gaql_cache(query=q1, api_version="v25", cache_path=cache_file) == 0

        # 2. Invalidate all entries for api_version="v25"
        vg.set_cached_validation(q1, "v25", cache_path=cache_file)
        removed_ver = vg.invalidate_gaql_cache(api_version="v25", cache_path=cache_file)
        assert removed_ver == 2
        assert vg.get_cached_validation(q1, "v25", cache_path=cache_file) is None
        assert vg.get_cached_validation(q2, "v25", cache_path=cache_file) is None
        assert vg.get_cached_validation(q3, "v24", cache_path=cache_file) is not None

        # 3. Full cache clear
        vg.set_cached_validation(q1, "v25", cache_path=cache_file)
        removed_all = vg.invalidate_gaql_cache(cache_path=cache_file)
        assert removed_all == 2
        assert vg.get_cached_validation(q1, "v25", cache_path=cache_file) is None
        assert vg.get_cached_validation(q3, "v24", cache_path=cache_file) is None

        # 4. Regression check: paths containing colons (e.g. Windows drive letters C:\...)
        win_path = r"C:\hostedtoolcache\windows\gaql_cache.json"
        orig_load = vg._load_disk_cache
        orig_save = vg._save_disk_cache
        with (
            patch.object(vg, "_get_cache_file_path", return_value=win_path),
            patch.object(vg, "_load_disk_cache", side_effect=lambda _p: orig_load(cache_file)),
            patch.object(vg, "_save_disk_cache", side_effect=lambda _p, d: orig_save(cache_file, d)),
        ):
            vg.set_cached_validation(q1, "v25", cache_path=win_path)
            vg.set_cached_validation(q3, "v24", cache_path=win_path)
            assert vg.invalidate_gaql_cache(cache_path=win_path) == 2

    def test_cache_ttl_expiration_invalidation(self, tmp_path):
        """Expired cache entries are automatically invalidated on read."""
        cache_file = str(tmp_path / "gaql_cache.json")
        query = "SELECT campaign.id FROM campaign"
        past_timestamp = time.time() - 120.0
        vg.set_cached_validation(
            query,
            "v25",
            valid=True,
            cache_path=cache_file,
            timestamp=past_timestamp,
        )

        # With TTL=300s, entry is still valid
        assert vg.get_cached_validation(query, "v25", cache_path=cache_file, ttl_seconds=300.0) is not None

        # With TTL=60s, entry is expired and purged from memory + disk
        assert vg.get_cached_validation(query, "v25", cache_path=cache_file, ttl_seconds=60.0) is None
        assert vg.get_cached_validation(query, "v25", cache_path=cache_file, ttl_seconds=300.0) is None

    def test_use_cache_false_bypasses_cache(self, tmp_path):
        """Passing use_cache=False always executes validation and does not read from cache."""
        cache_file = str(tmp_path / "gaql_cache.json")
        mock_client = MagicMock()
        mock_service = MagicMock()
        mock_client.get_service.return_value = mock_service
        query = "SELECT campaign.id FROM campaign"

        vg.validate_gaql(
            "1234567890",
            "v25",
            query,
            client=mock_client,
            use_cache=True,
            cache_path=cache_file,
        )
        assert mock_service.search.call_count == 1

        # With use_cache=False, it must bypass the cached entry and call ga_service.search again
        vg.validate_gaql(
            "1234567890",
            "v25",
            query,
            client=mock_client,
            use_cache=False,
            cache_path=cache_file,
        )
        assert mock_service.search.call_count == 2

    def test_cli_clear_cache_and_no_cache_flags(self, tmp_path):
        """CLI main() supports --clear-cache, --no-cache, and --cache-path flags."""
        cache_file = str(tmp_path / "cli_gaql_cache.json")
        query = "SELECT campaign.id FROM campaign"
        vg.set_cached_validation(query, "v25", cache_path=cache_file)
        assert vg.get_cached_validation(query, "v25", cache_path=cache_file) is not None

        with patch.object(
            sys,
            "argv",
            [
                "validate_gaql.py",
                "--customer_id",
                "1234567890",
                "--api_version",
                "v25",
                "--query",
                query,
                "--clear-cache",
                "--no-cache",
                "--cache-path",
                cache_file,
            ],
        ), patch.object(vg, "validate_gaql") as mock_validate:
            vg.main()
            # --clear-cache should have invalidated the pre-existing entry
            assert vg.get_cached_validation(query, "v25", cache_path=cache_file) is None
            mock_validate.assert_called_once_with(
                "1234567890",
                "v25",
                query,
                use_cache=False,
                cache_path=cache_file,
                cache_ttl=vg.DEFAULT_CACHE_TTL_SECONDS,
            )
