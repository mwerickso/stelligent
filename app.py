from flask import Flask, jsonify, Response
from flask_restful import Resource, Api
from time import time

app = Flask(__name__)
api = Api(app)

class Message(Resource):
    def get(self):
        response = {'message':'Automation for the People', 'timestamp': time()}
        return jsonify(response)

api.add_resource(Message, '/message')

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=80)
