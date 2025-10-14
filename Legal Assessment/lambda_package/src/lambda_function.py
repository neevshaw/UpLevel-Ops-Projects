import sys
import os

# Add lib folder to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))

from src.app import app, process, process2, process3
import serverless_wsgi as serverless_wsgi

def handler(event, context):
    if event.get('worker'):
        # This is a background task, not an HTTP request
        
        task_type = event.get('task_type')
        data = event.get('data')
        
        # Process the long-running task
        if task_type == 'file_processing':
            process(data)
        elif task_type == 'score_baseline':
            process2(data)
        elif task_type == 'policy':
            process3(data)
        # Add more task types as needed
        
        return {'status': 200, 'body': 'Worker completed'}
    
    # Otherwise, handle as normal Flask HTTP request
    return serverless_wsgi.handle_request(app, event, context)