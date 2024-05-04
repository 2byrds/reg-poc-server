FROM 2byrds/keri:1.1.7

WORKDIR /usr/local/var

RUN mkdir server
COPY . /usr/local/var/server
RUN ls -la /usr/local/var/server
WORKDIR /usr/local/var/server/

RUN pip install -r requirements.txt

WORKDIR /usr/local/var/server/src/regps

ENV KERI_AGENT_CORS=true

ENTRYPOINT [ "gunicorn", "-b", "0.0.0.0:8000", "app:app"]
