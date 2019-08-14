FROM python:3.6

RUN apt-get update; apt-get -y upgrade;
WORKDIR /app
COPY . /app
RUN pip install -r requirements.txt

EXPOSE 80
CMD ["python3", "app.py"]
