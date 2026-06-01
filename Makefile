.PHONY: install run-etl dashboard test sql-check clean

install:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt

run-etl:
	python3 etl/process_billing_data.py

dashboard:
	.venv/bin/streamlit run dashboard/app.py

test:
	python3 -m unittest discover -s tests

sql-check:
	for file in sql/*.sql; do sqlite3 data/processed/cloud_costs.db < "$$file" > /dev/null; done

clean:
	find data/processed -type f -delete
