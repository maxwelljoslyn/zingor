"""Tests for the plane geometry under building designs (#197)."""

import math

from django.test import SimpleTestCase

from characters.geometry import (
    GeometryError,
    convex_overlap_area,
    is_simple,
    overlap_area,
    polygon_area,
    polyline_length,
    segment_spans,
    triangulate,
    wall_pieces,
)

SQUARE = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]


class LengthAndAreaTests(SimpleTestCase):
    def test_polyline_length_open_and_closed(self):
        self.assertEqual(polyline_length(SQUARE, closed=False), 30)
        self.assertEqual(polyline_length(SQUARE, closed=True), 40)

    def test_a_diagonal_costs_its_true_length(self):
        """The reason for shapes over cells: a 45° run is √2 per step, not 2."""
        self.assertAlmostEqual(
            polyline_length([(0, 0), (5, 5)], closed=False), 5 * math.sqrt(2)
        )

    def test_segment_spans(self):
        self.assertEqual(
            segment_spans([(0, 0), (10, 0), (10, 5)], closed=False),
            [(0, 10), (10, 15)],
        )

    def test_polygon_area_either_winding(self):
        self.assertEqual(polygon_area(SQUARE), 100)
        self.assertEqual(polygon_area(list(reversed(SQUARE))), 100)


class SimplicityTests(SimpleTestCase):
    def test_square_is_simple(self):
        self.assertTrue(is_simple(SQUARE, closed=True))

    def test_bowtie_is_not(self):
        self.assertFalse(is_simple([(0, 0), (10, 10), (10, 0), (0, 10)], closed=True))

    def test_folding_back_is_not(self):
        self.assertFalse(is_simple([(0, 0), (10, 0), (5, 0)], closed=False))

    def test_touching_itself_is_not(self):
        self.assertFalse(is_simple([(0, 0), (10, 0), (10, 10), (5, 0)], closed=False))


class WallPieceTests(SimpleTestCase):
    def test_straight_wall_is_a_rectangle(self):
        (piece,) = wall_pieces([(0, 0), (10, 0)], 2, closed=False)
        self.assertEqual(sorted(piece), [(0, -1), (0, 1), (10, -1), (10, 1)])

    def test_pieces_total_length_times_thickness(self):
        """Mitred corners neither add nor lose area, open or closed."""
        for closed in (False, True):
            pieces = wall_pieces(SQUARE, 1, closed)
            area = sum(polygon_area(piece) for piece in pieces)
            self.assertAlmostEqual(area, polyline_length(SQUARE, closed) * 1)

    def test_diagonal_corner_keeps_the_same_rule(self):
        points = [(0, 0), (10, 0), (20, 10)]
        pieces = wall_pieces(points, 2, closed=False)
        area = sum(polygon_area(piece) for piece in pieces)
        self.assertAlmostEqual(area, polyline_length(points, False) * 2)

    def test_neighbouring_pieces_meet_without_overlapping(self):
        first, second = wall_pieces([(0, 0), (10, 0), (10, 10)], 2, closed=False)
        self.assertAlmostEqual(convex_overlap_area(first, second), 0)

    def test_pieces_are_counter_clockwise(self):
        for piece in wall_pieces([(0, 0), (10, 0), (20, 10)], 2, closed=False):
            points = piece
            signed = sum(
                points[i][0] * points[(i + 1) % 4][1]
                - points[(i + 1) % 4][0] * points[i][1]
                for i in range(4)
            )
            self.assertGreater(signed, 0)

    def test_a_hairpin_is_refused(self):
        with self.assertRaises(GeometryError):
            wall_pieces([(0, 0), (10, 0), (0, 1)], 1, closed=False)

    def test_a_segment_shorter_than_its_mitres_is_refused(self):
        with self.assertRaises(GeometryError):
            wall_pieces([(0, 0), (10, 0), (10, 0.5), (0, 0.5)], 2, closed=False)

    def test_coincident_points_are_refused(self):
        with self.assertRaises(GeometryError):
            wall_pieces([(0, 0), (0, 0)], 1, closed=False)


class OverlapTests(SimpleTestCase):
    def test_convex_overlap(self):
        other = [(5.0, 5.0), (15.0, 5.0), (15.0, 15.0), (5.0, 15.0)]
        self.assertAlmostEqual(convex_overlap_area(SQUARE, other), 25)

    def test_shared_edge_is_no_overlap(self):
        beside = [(10.0, 0.0), (20.0, 0.0), (20.0, 10.0), (10.0, 10.0)]
        self.assertAlmostEqual(convex_overlap_area(SQUARE, beside), 0)

    def test_half_shifted_squares_overlap(self):
        """Collinear edges and vertices on edges must not hide a real overlap."""
        shifted = [(5.0, 0.0), (15.0, 0.0), (15.0, 10.0), (5.0, 10.0)]
        self.assertAlmostEqual(convex_overlap_area(SQUARE, shifted), 50)

    def test_triangulation_keeps_area(self):
        l_shape = [(0, 0), (10, 0), (10, 4), (4, 4), (4, 10), (0, 10)]
        triangles = triangulate(l_shape)
        self.assertAlmostEqual(sum(polygon_area(t) for t in triangles), 64)

    def test_triangulation_skips_points_along_an_edge(self):
        with_midpoint = [(0, 0), (5, 0), (10, 0), (10, 10), (0, 10)]
        triangles = triangulate(with_midpoint)
        self.assertAlmostEqual(sum(polygon_area(t) for t in triangles), 100)

    def test_concave_shapes_overlap_only_where_they_do(self):
        l_shape = [(0, 0), (10, 0), (10, 4), (4, 4), (4, 10), (0, 10)]
        in_the_notch = [(5, 5), (9, 5), (9, 9), (5, 9)]
        self.assertAlmostEqual(
            overlap_area(triangulate(l_shape), triangulate(in_the_notch)), 0
        )
        straddling = [(2, 2), (6, 2), (6, 6), (2, 6)]
        self.assertAlmostEqual(
            overlap_area(triangulate(l_shape), triangulate(straddling)), 12
        )

    def test_butt_joint_touches_the_face_without_overlap(self):
        """A wall stopped at another's face shares no area with it."""
        long_wall = wall_pieces([(0, 0), (20, 0)], 2, closed=False)
        butting = wall_pieces([(10, 1), (10, 10)], 1, closed=False)
        self.assertAlmostEqual(overlap_area(long_wall, butting), 0)

    def test_wall_run_to_the_centreline_overlaps(self):
        long_wall = wall_pieces([(0, 0), (20, 0)], 2, closed=False)
        to_centre = wall_pieces([(10, 0), (10, 10)], 1, closed=False)
        self.assertAlmostEqual(overlap_area(long_wall, to_centre), 1)
