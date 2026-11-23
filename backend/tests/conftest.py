"""Test compatibility shims."""

import inspect

from mongomock.collection import BulkOperationBuilder

# pymongo>=4.9 passes ``sort`` to bulk UpdateOne; mongomock 4.3 predates it.
if "sort" not in inspect.signature(BulkOperationBuilder.add_update).parameters:
    _add_update = BulkOperationBuilder.add_update

    def _add_update_ignoring_sort(self, *args, sort=None, **kwargs):
        return _add_update(self, *args, **kwargs)

    BulkOperationBuilder.add_update = _add_update_ignoring_sort
