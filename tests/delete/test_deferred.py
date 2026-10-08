from django.db import connection
from django.db.models import signals
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from .models import R, S, T


class DeleteRelatedFieldsTests(TestCase):
    def _related_select(self):
        """
        Delete an R cascading to S (which isn't fast-deletable since T points
        to it) and return the SELECT run against S's table.
        """
        r = R.objects.create()
        s = S.objects.create(r=r)
        T.objects.create(s=s)
        table = connection.ops.quote_name(S._meta.db_table)
        with CaptureQueriesContext(connection) as ctx:
            r.delete()
        selects = [
            q['sql'] for q in ctx.captured_queries
            if q['sql'].startswith('SELECT') and ' FROM %s ' % table in q['sql']
        ]
        self.assertEqual(len(selects), 1, selects)
        self.assertFalse(S.objects.exists())
        self.assertFalse(T.objects.exists())
        return selects[0]

    def _column(self, name):
        return '%s.%s' % (
            connection.ops.quote_name(S._meta.db_table),
            connection.ops.quote_name(name),
        )

    def test_only_referenced_fields_selected(self):
        sql = self._related_select()
        select_list = sql.split(' FROM ')[0]
        self.assertIn(self._column('id'), select_list)
        self.assertNotIn(self._column('r_id'), select_list)

    def test_all_fields_selected_with_delete_signal(self):
        def receiver(instance, **kwargs):
            pass

        for signal in (signals.pre_delete, signals.post_delete):
            with self.subTest(signal=signal):
                signal.connect(receiver, sender=S)
                try:
                    sql = self._related_select()
                finally:
                    signal.disconnect(receiver, sender=S)
                select_list = sql.split(' FROM ')[0]
                self.assertIn(self._column('id'), select_list)
                self.assertIn(self._column('r_id'), select_list)
