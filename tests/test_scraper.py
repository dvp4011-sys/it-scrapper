import copy
import unittest
from unittest.mock import MagicMock
from scraper import canonical, evaluate, parse_offer, postings, Sheets

PROFILE = {'city':'Rzeszów','remote':True,'minimum_monthly_pln':10000,'hourly_month_hours':160,'minimum_score':25,'unconfirmed':['Kotlin']}
BASE = {'title':'Android Java Developer','description':'PAX POS printers payment Kotlin','jobLocationType':'TELECOMMUTE','hiringOrganization':{'name':'Example'},'baseSalary':{'currency':'PLN','value':{'minValue':80,'maxValue':100,'unitText':'HOUR'}}}

class ScraperTests(unittest.TestCase):
    def job(self, **updates):
        data = copy.deepcopy(BASE)
        data.update(updates)
        return parse_offer(data,'https://example.com/job/1?promo=one','test')

    def test_nested_json_ld(self):
        html = '<script type="application/ld+json">{"@graph":[{"@type":["JobPosting"],"title":"Android"}]}</script>'
        self.assertEqual(list(postings(html))[0]['title'],'Android')

    def test_salary_hourly_and_unknown_skill(self):
        match = evaluate(self.job(),PROFILE)
        self.assertIsNotNone(match)
        self.assertIn('Kotlin — do potwierdzenia',match['gaps'])

    def test_salary_below_minimum(self):
        job = self.job(baseSalary={'currency':'PLN','value':{'maxValue':9000,'unitText':'MONTH'}})
        self.assertIsNone(evaluate(job,PROFILE))

    def test_unknown_salary_kept(self):
        self.assertIsNotNone(evaluate(self.job(baseSalary=None),PROFILE))

    def test_foreign_currency_not_compared_as_pln(self):
        job = self.job(baseSalary={'currency':'EUR','value':{'maxValue':5000,'unitText':'MONTH'}})
        self.assertIn('Płaca do weryfikacji',evaluate(job,PROFILE)['reasons'])

    def test_city_and_remote(self):
        self.assertIsNone(evaluate(self.job(jobLocationType='',jobLocation={'address':{'addressLocality':'Warszawa'}}),PROFILE))
        self.assertIsNotNone(evaluate(self.job(jobLocationType='',jobLocation={'address':{'addressLocality':'Rzeszów'}}),PROFILE))

    def test_backend_java_not_matched(self):
        self.assertIsNone(evaluate(self.job(title='Java Backend Developer',description='Spring payments'),PROFILE))

    def test_expired_offer(self):
        self.assertIsNone(evaluate(self.job(validThrough='2020-01-01'),PROFILE))

    def test_dedup_canonical_link(self):
        self.assertEqual(canonical('https://example.com/job/1/?promo=x'),'https://example.com/job/1')

    def test_sheet_append_does_not_update_manual_fields(self):
        sheet = Sheets.__new__(Sheets)
        sheet.api, sheet.id = MagicMock(),'example'
        sheet.append('Oferty',[['=untrusted title']])
        sheet.api.values.return_value.append.assert_called_once()
        self.assertEqual(sheet.api.values.return_value.append.call_args.kwargs['valueInputOption'],'RAW')
        sheet.api.values.return_value.update.assert_not_called()

if __name__ == '__main__':
    unittest.main()
