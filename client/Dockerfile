FROM python:3.9
COPY . /usr/src/app
WORKDIR /usr/src/app
RUN pip install -r requirements.txt
EXPOSE 8000
CMD ["python", "main.py"]