#!/usr/bin/env python3
"""验证体验评分的失败惩罚与逐任务回归门槛。"""

import copy
import unittest

import experience


def row(**changes):
    item = dict(id='one', text='你好', keys='nihao', position=0, completed=True,
                actions=6, stable=True, page_turns=0, query_ms=[1, 2, 3])
    item.update(changes)
    return item


class ExperienceTests(unittest.TestCase):
    def test_perfect_typing_scores_one_hundred(self):
        report = experience.summarize([row()], [dict(passed=True)])
        self.assertEqual(report['score'], 100)

    def test_failed_tasks_reduce_accuracy_completion_and_efficiency(self):
        failed = row(position=None, completed=False, actions=1)
        report = experience.summarize([row(), failed], [dict(passed=True)])
        self.assertEqual(report['completion'], .5)
        self.assertEqual(report['efficiency'], .5)
        self.assertLess(report['score'], 75)

    def test_pages_and_selection_actions_cost_points(self):
        report = experience.summarize([row(actions=16, page_turns=10)], [dict(passed=True)])
        self.assertLess(report['score_parts']['efficiency'], 10)
        self.assertEqual(report['total_page_turns'], 10)

    def test_failed_learning_cannot_be_offset_by_accuracy(self):
        report = experience.summarize([row()], [dict(passed=False)])
        self.assertEqual(report['score_parts']['interactions'], 0)
        self.assertEqual(report['score'], 80)

    def test_top1_top5_and_completion_are_independent_gates(self):
        previous = dict(results=[row()])
        after = copy.deepcopy(previous['results'])
        after[0].update(position=8, completed=False)
        failures = experience.compare(after, previous)
        self.assertEqual({r['metric'] for r in failures}, {'top1', 'top5', 'completion'})

    def test_previously_failed_tasks_can_improve_without_changing_baseline(self):
        previous = dict(results=[row(position=None, completed=False)])
        self.assertEqual(experience.compare([row()], previous), [])


if __name__ == '__main__':
    unittest.main()
