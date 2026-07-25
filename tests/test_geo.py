from app.core.geo import haversine_m


def test_same_point_is_zero():
    assert haversine_m(37.5665, 126.978, 37.5665, 126.978) == 0


def test_one_degree_latitude_is_about_111km():
    # 위도 1도 ≈ 111.19km
    assert abs(haversine_m(0.0, 0.0, 1.0, 0.0) - 111_195) < 200


def test_small_distance_precision():
    # 위도 방향 약 20m 이동 (1도 ≈ 111,320m)
    lat = 37.5665
    dist = haversine_m(lat, 126.978, lat + 20 / 111_320, 126.978)
    assert abs(dist - 20) < 0.1
