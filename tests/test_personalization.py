"""Verify independent retry behavior for multiple administrator recipients."""
import importlib.util
import json
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('personalized_mail', ROOT/'lambda/order_email/handler.py')
mail = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mail)
class MultiAdminTests(unittest.TestCase):
    def data(self):
        return dict(schemaVersion=1,eventType='ORDER_CREATED',eventId='12345678-1234-1234-1234-123456789012',orderId=1,memberId=1,quantity=1,total=10,productName='test',recipientEmail='buyer@example.com')
    def test_unique_keys_and_duplicate_admin_input(self):
        targets=list(mail.delivery_targets(self.data(),['a@example.com','b@example.com','a@example.com']))
        self.assertEqual(len(targets),3)
        self.assertEqual(len(set(key for key,_ in targets)),3)
    def test_retry_only_sends_failed_administrator(self):
        class Store:
            def __init__(self): self.done=set()
            def claim(self,key,token,now): return key not in self.done
            def sent(self,key,token): self.done.add(key)
            def release(self,key,token): pass
        store=Store();sent=[];failing=True
        def send(data):
            if failing and data['recipientEmail']=='b@example.com': raise RuntimeError('mock failure')
            sent.append(data['recipientEmail'])
        event={'Records':[{'messageId':'message-1','body':json.dumps(self.data())}]}
        admins=['a@example.com','b@example.com']
        self.assertEqual(mail.process(event,store,send,admin_email=admins)['batchItemFailures'],[{'itemIdentifier':'message-1'}])
        failing=False
        self.assertEqual(mail.process(event,store,send,admin_email=admins)['batchItemFailures'],[])
        self.assertEqual(sent,['buyer@example.com','a@example.com','b@example.com'])
    def test_invalid_recipient_prevents_any_delivery(self):
        class Store:
            def claim(self,*args): raise AssertionError('must validate before claiming')
        event={'Records':[{'messageId':'message-1','body':json.dumps(self.data())}]}
        result=mail.process(event,Store(),lambda d:self.fail('must not send'),admin_email=['a@example.com','bad'])
        self.assertEqual(result['batchItemFailures'],[{'itemIdentifier':'message-1'}])
if __name__=='__main__':unittest.main()
