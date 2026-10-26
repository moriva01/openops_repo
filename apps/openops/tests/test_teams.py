import unittest
from unittest.mock import patch, MagicMock
from receiver.notifications import teams_card, send


class TeamsTests(unittest.TestCase):
    def payload(self, action):
        return {'schema':'openops.notification.v1','alert_id':7,'action':action,'severity':'clear' if action=='resolved' else 'critical',
                'monitor':'CPU utilization','host_id':'private-internal-id','host_name':'Demo server',
                'evidence':{'metric':'cpu_percent','value':98,'event_id':'sample-123'}}

    def test_opening_and_recovery_have_distinct_adaptive_cards(self):
        for action,color,title in [('opened','Attention','ALERT'),('resolved','Good','RECOVERED')]:
            card=teams_card(self.payload(action))
            self.assertEqual(card['type'],'message')
            attachment=card['attachments'][0]
            self.assertEqual(attachment['contentType'],'application/vnd.microsoft.card.adaptive')
            body=attachment['content']['body']
            self.assertEqual(body[0]['color'],color)
            self.assertIn(title,body[0]['text'])
            self.assertEqual(body[-1]['facts'][0]['value'],'7')
            self.assertNotIn('private-internal-id',str(card))

    def test_connection_test_cannot_look_like_real_incident(self):
        card=teams_card({**self.payload('test'),'test':True})
        self.assertIn('TEST',card['attachments'][0]['content']['body'][0]['text'])
        self.assertIn('No incident',card['attachments'][0]['content']['body'][1]['text'])

    def test_sends_teams_envelope_and_records_http_acceptance(self):
        response=MagicMock();response.status=202
        response.__enter__.return_value=response
        opener=MagicMock();opener.open.return_value=response
        with patch('receiver.notifications.urllib.request.build_opener',return_value=opener):
            status=send({'kind':'teams','config':{'url':'https://example.test/workflow'},'secret':''},self.payload('opened'),42)
        import json
        request=opener.open.call_args.args[0]
        self.assertEqual(json.loads(request.data)['type'],'message')
        self.assertEqual(status,202)
