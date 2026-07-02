"""Investment information system service package.

The fetch job is executed by the existing ``TaskJob`` worker (see
``task_worker.py``) via ``InvestmentFetchJobHandler`` (added in Task 4); this
package only contains the synchronous CRUD/dashboard service and (later) the
fetcher/normalizer/classifier pieces.
"""
