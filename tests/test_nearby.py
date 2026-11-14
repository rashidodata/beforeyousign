from beforeyousign.nearby import classify, parse_places, distance_m, overpass_query


def test_distance():
    assert distance_m(40.42, -3.71, 40.42, -3.71) == 0
    assert 820 < distance_m(40.42, -3.71, 40.429, -3.71) < 1100


def test_school_market_and_dedupe():
    payload = {'elements': [
        {'type': 'node', 'id': 1, 'lat': 40.42, 'lon': -3.71, 'tags': {'amenity': 'school', 'name': 'A School'}},
        {'type': 'node', 'id': 1, 'lat': 40.42, 'lon': -3.71, 'tags': {'amenity': 'school', 'name': 'A School'}},
        {'type': 'way', 'id': 2, 'center': {'lat': 40.421, 'lon': -3.71}, 'tags': {'shop': 'supermarket', 'name': 'Market'}},
    ]}
    result = parse_places(payload, 40.42, -3.71)
    assert len(result) == 2
    assert result[0]['category'] == 'Schools & nurseries'
    assert result[1]['category'] == 'Markets & groceries'
    assert result[1]['source_url'] == 'https://www.openstreetmap.org/way/2'


def test_query_has_school_and_market():
    query = overpass_query(40.42, -3.71)
    assert '["amenity"="school"]' in query
    assert '["amenity"="marketplace"]' in query
    assert '["shop"~' in query


def test_classification():
    assert classify({'amenity': 'kindergarten'}) == 'Schools & nurseries'
    assert classify({'shop': 'supermarket'}) == 'Markets & groceries'
    assert classify({'leisure': 'park'}) == 'Parks'