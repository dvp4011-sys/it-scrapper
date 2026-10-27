import copy
import unittest
from unittest.mock import MagicMock
from candidate_profile import default_rows, parse_profile, rank_keywords, aliases_match
from scraper import Sheets, HEADERS

class ProfileTests(unittest.TestCase):
    def test_sheet_weight_and_level_change_score(self):
        rows=default_rows()
        p=parse_profile(rows)
        before=rank_keywords('Android Java Developer','PAX POS',p)[0]
        pax=next(r for r in rows if r[1]=='PAX')
        pax[4]=100
        pax[5]=5
        after=rank_keywords('Android Java Developer','PAX POS',parse_profile(rows))[0]
        self.assertGreater(after,before)

    def test_custom_skill_can_be_added_without_code(self):
        rows=default_rows()
        rows.append(['własne','Czytniki NFC','nfc|near field communication','',30,4,3,'TAK','całość',''])
        result=rank_keywords('Android Developer','NFC',parse_profile(rows))
        self.assertTrue(any('Czytniki NFC: +24' in r for r in result[1]))

    def test_unknown_skill_does_not_award_points(self):
        result=rank_keywords('Android Kotlin Developer','',parse_profile(default_rows()))
        self.assertEqual(result[0],18.75)
        self.assertIn('Kotlin — do potwierdzenia',result[2])

    def test_disabled_rule_and_literal_word_boundaries(self):
        rows=default_rows();next(r for r in rows if r[1]=='PAX')[7]='NIE'
        result=rank_keywords('Android Developer','PAX',parse_profile(rows))
        self.assertEqual(result[0],18.75)
        self.assertFalse(aliases_match(['java'],'JavaScript'))
        self.assertFalse(aliases_match(['pos'],'position'))
        self.assertTrue(aliases_match(['C#'],'C# developer'))

    def test_invalid_value_reports_sheet_row(self):
        rows=default_rows();rows[1][7]='maybe'
        with self.assertRaisesRegex(ValueError,'wiersz 2'):
            parse_profile(rows)

    def test_missing_settings_and_duplicate_rows_fail(self):
        with self.assertRaisesRegex(ValueError,'brakuje'):
            parse_profile([default_rows()[0]])
        rows=default_rows();rows.append(copy.deepcopy(rows[1]))
        with self.assertRaisesRegex(ValueError,'Powtórzona'):
            parse_profile(rows)

    def test_existing_profile_never_reseeded(self):
        sheet=Sheets.__new__(Sheets);sheet.api=MagicMock();sheet.id='example'
        sheet.api.get.return_value.execute.return_value={'sheets':[{'properties':{'title':'Profil'}}]}
        sheet.read=MagicMock(return_value=default_rows())
        sheet.append=MagicMock()
        sheet.load_profile()
        sheet.append.assert_not_called()
        sheet.api.batchUpdate.assert_not_called()

    def test_reordered_offer_columns_are_mapped_by_name(self):
        sheet=Sheets.__new__(Sheets);sheet.api=MagicMock();sheet.id='example'
        sheet.offer_headers=HEADERS.copy()
        sheet.offer_headers.remove('Match');sheet.offer_headers.insert(5,'Match')
        row=['']*len(HEADERS);row[HEADERS.index('Match')]='75%';row[HEADERS.index('Wysłano CV')]='2026-10-27'
        sheet.append('Oferty',[row])
        values=sheet.api.values.return_value.append.call_args.kwargs['body']['values'][0]
        self.assertEqual(values[5],'75%')
        self.assertEqual(values[6],'2026-10-27')

    def test_later_rows_are_read(self):
        rows=default_rows()+[[''] for _ in range(1000)]
        rows.append(['własne','Nowy wpis','customterm','',10,5,1,'TAK','całość',''])
        result=rank_keywords('Android Developer','customterm',parse_profile(rows))
        self.assertTrue(any('Nowy wpis' in r for r in result[1]))

if __name__=='__main__':unittest.main()
