"""Tests for the PartFetcher class."""

import pytest
from unittest.mock import Mock, patch
from lego_labels.fetcher import PartFetcher


class TestPartFetcher:
    """Test cases for PartFetcher."""

    def test_init(self):
        """Test PartFetcher initialization."""
        fetcher = PartFetcher(verbose=True)
        assert fetcher.verbose is True

    @patch('lego_labels.fetcher.requests.Session.get')
    def test_fetch_part_info_success(self, mock_get):
        """Test successful part info fetch."""
        # Mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b'<html><title>Brick 2 x 2 (Part 3003) | BrickArchitect</title></html>'
        mock_get.return_value = mock_response

        fetcher = PartFetcher()
        with patch.object(fetcher, 'download_image', return_value='/path/to/image.png'):
            info = fetcher.fetch_part_info('3003')

        assert info is not None
        assert info['reference'] == '3003'
        assert 'Brick 2 x 2' in info['title']
        assert info['image_path'] == '/path/to/image.png'

    @patch('lego_labels.fetcher.requests.Session.get')
    def test_fetch_part_info_not_found(self, mock_get):
        """Test 404 handling."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        fetcher = PartFetcher()
        info = fetcher.fetch_part_info('99999')

        assert info is None

    def test_fetch_multiple_parts(self):
        """Test fetching multiple parts."""
        fetcher = PartFetcher()

        with patch.object(fetcher, 'fetch_part_info') as mock_fetch:
            mock_fetch.side_effect = [
                {'title': 'Part 1', 'reference': '3001', 'image_path': '/path1.png'},
                {'title': 'Part 2', 'reference': '3002', 'image_path': '/path2.png'},
                None  # Failed fetch
            ]

            parts = fetcher.fetch_multiple_parts(['3001', '3002', '3003'])

        assert len(parts) == 2
        assert parts[0]['reference'] == '3001'
        assert parts[1]['reference'] == '3002'
