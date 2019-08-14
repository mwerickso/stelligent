import os
import sys
import inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0,parentdir) 

from unittest import TestCase, mock, main
from time import time
import app

class test_message(TestCase):
    @mock.patch('app.jsonify')
    def test_get(self, mock_jsonify):
        timestamp = time()
        mock_jsonify.return_value = {'message':'Automation for the People', 'timestamp': timestamp}
        message = app.Message()
        response = message.get()
        self.assertEqual(response, {'message':'Automation for the People', 'timestamp': timestamp})

if __name__ == '__main__':
    main()
