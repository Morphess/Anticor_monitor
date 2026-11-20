import os
import unittest
from datetime import date
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from app.models.risk import Risk
from app.models.risk_assessment import RiskAssessment

@unittest.skipUnless(os.getenv('ORDER_TEST_DATABASE_URL'), 'Disposable PostgreSQL URL not supplied')
class RiskAssessmentIntegrityTests(unittest.TestCase):
    def test_final_assessment_cannot_be_rewritten(self):
        engine=create_engine(os.environ['ORDER_TEST_DATABASE_URL'])
        try:
            with Session(engine) as db:
                risk=Risk(id='SYNTRA01',process_name='Synthetic',title='Synthetic risk',
                    description='Synthetic test',risk_sources='Test',existing_controls='Test',
                    probability_score=1,impact_score=2,score=2,level='low',
                    indicator_name='Test',indicator_unit='unit',indicator_direction='decrease',
                    indicator_baseline_value=10,indicator_target_value=1,target_date=date(2026,12,31))
                db.add(risk);db.flush()
                row=RiskAssessment(risk_id=risk.id,kind='baseline',status='approved',
                    assessed_on=date(2026,11,20),probability_score=1,impact_score=2,
                    score=2,level='low',justification='Synthetic baseline assessment for trigger test')
                db.add(row);db.flush()
                for sql in ('UPDATE risk_assessments SET score=3 WHERE id=:id',
                            'DELETE FROM risk_assessments WHERE id=:id'):
                    with self.assertRaises(DBAPIError):
                        with db.begin_nested():db.execute(text(sql),{'id':row.id})
                self.assertEqual(db.scalar(text('SELECT score FROM risk_assessments WHERE id=:id'),{'id':row.id}),2)
                db.rollback()
        finally:engine.dispose()
