import pytest
import ray

from eos.utils.ray_utils import RayActorWrapper


@ray.remote
class DummyActor:
    def __init__(self):
        self.value = 0

    def reset_value(self):
        self.value = 0

    def increment(self, amount=1):
        self.value += amount
        return self.value

    def get_value(self):
        return self.value


class TestRayActorWrapper:
    @pytest.fixture(scope="class")
    def dummy_actor(self):
        actor = DummyActor.remote()
        yield actor
        ray.kill(actor)

    @pytest.fixture(scope="class")
    def wrapped_actor(self, dummy_actor):
        return RayActorWrapper(dummy_actor)

    def test_method_call(self, wrapped_actor):
        wrapped_actor.reset_value()
        result = wrapped_actor.increment()
        assert result == 1

    def test_method_call_with_args(self, wrapped_actor):
        wrapped_actor.reset_value()
        result = wrapped_actor.increment(5)
        assert result == 5

    def test_multiple_method_calls(self, wrapped_actor):
        wrapped_actor.reset_value()
        wrapped_actor.increment()
        wrapped_actor.increment(4)
        result = wrapped_actor.get_value()
        assert result == 5

    def test_nonexistent_method(self, wrapped_actor):
        with pytest.raises(AttributeError):
            wrapped_actor.nonexistent_method()

    def test_wrapped_actor_no_independence(self, dummy_actor):
        wrapped_actor1 = RayActorWrapper(dummy_actor)
        wrapped_actor2 = RayActorWrapper(dummy_actor)

        wrapped_actor1.reset_value()
        wrapped_actor1.increment(2)
        result = wrapped_actor2.get_value()
        assert result == 2

    def test_actor_property(self, wrapped_actor, dummy_actor):
        assert wrapped_actor.actor == dummy_actor
