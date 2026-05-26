import threading
from tools.status_tracker import CrewStatusTracker


class TestCrewStatusTracker:
    """Test the SSE status tracker module."""

    def test_create_task(self):
        tracker = CrewStatusTracker()
        task_id = tracker.create_task()
        assert isinstance(task_id, str)
        assert len(task_id) == 8  # UUID[:8]
        tracker.cleanup(task_id)

    def test_create_multiple_tasks(self):
        tracker = CrewStatusTracker()
        t1 = tracker.create_task()
        t2 = tracker.create_task()
        assert t1 != t2
        tracker.cleanup(t1)
        tracker.cleanup(t2)

    def test_update_and_retrieve(self):
        tracker = CrewStatusTracker()
        task_id = tracker.create_task()
        tracker.update(task_id, "starting", "Searching...")

        updates = tracker.get_updates(task_id)
        msg = next(updates)
        assert msg["step"] == "starting"
        assert msg["detail"] == "Searching..."
        assert "timestamp" in msg
        tracker.cleanup(task_id)

    def test_multiple_updates(self):
        tracker = CrewStatusTracker()
        task_id = tracker.create_task()

        tracker.update(task_id, "starting", "step 1")
        tracker.update(task_id, "generating", "step 2")
        tracker.update(task_id, "complete", "done")

        updates = tracker.get_updates(task_id)
        m1 = next(updates)
        m2 = next(updates)
        m3 = next(updates)

        assert m1["step"] == "starting"
        assert m2["step"] == "generating"
        assert m3["step"] == "complete"
        tracker.cleanup(task_id)

    def test_cleanup(self):
        tracker = CrewStatusTracker()
        task_id = tracker.create_task()
        tracker.cleanup(task_id)
        # Verify no error on double cleanup
        tracker.cleanup(task_id)
        # Update to nonexistent task should not raise
        tracker.update(task_id, "step", "detail")

    def test_concurrent_updates(self):
        tracker = CrewStatusTracker()
        task_id = tracker.create_task()

        def worker(step_name):
            for i in range(5):
                tracker.update(task_id, step_name, f"detail {i}")

        t1 = threading.Thread(target=worker, args=("worker1",))
        t2 = threading.Thread(target=worker, args=("worker2",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        count = 0
        for msg in tracker.get_updates(task_id):
            if msg["step"] != "heartbeat":
                count += 1
            if count >= 10:
                break

        assert count == 10
        tracker.cleanup(task_id)
