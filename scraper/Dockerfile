FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY buildconnect_scraper ./buildconnect_scraper
COPY seeds.example.txt ./
ENTRYPOINT ["python", "-m", "buildconnect_scraper"]
CMD ["--seeds-file", "seeds.example.txt"]
