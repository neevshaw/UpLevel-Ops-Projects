import sys
import os

# Vendored dependencies live in ../lib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))

from src.app import app, process, process2, process3
import serverless_wsgi as serverless_wsgi

def handler(event, context):
    if event.get('worker'):
        # Background task invoked asynchronously by this same function
        task_type = event.get('task_type')
        data = event.get('data')

        if task_type == 'file_processing':
            process(data)
        elif task_type == 'score_baseline':
            process2(data)
        elif task_type == 'policy':
            process3(data)

        return {'status': 200, 'body': 'Worker completed'}
    
    return serverless_wsgi.handle_request(app, event, context)