from cvt_simulator.main import simulate_cvt_model

def test_simulate_cvt_model():
    input_data = {}
    result = simulate_cvt_model(input_data)
    assert result == {"result": "Received: test input"}
    print("Test passed!")

test_simulate_cvt_model()