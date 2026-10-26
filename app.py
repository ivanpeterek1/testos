"""Jednoduchý webový dotazník ukládající odpovědi do PostgreSQL.

Pro připojení použijte proměnnou prostředí DATABASE_URL, například:
postgresql://postgres:heslo@db:5432/dotaznik
"""

import os
from contextlib import closing

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from flask import Flask, redirect, render_template_string, request, url_for
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, Length

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY") or os.urandom(32)
DATABASE_URL = os.getenv(
	"DATABASE_URL", "postgresql://postgres:postgres@db:5432/dotaznik"
)


class QuestionnaireForm(FlaskForm):
	name = StringField(
		"Jméno",
		filters=[lambda value: value.strip() if isinstance(value, str) else value],
		validators=[
			DataRequired(message="Vyplňte jméno."),
			Length(max=100, message="Jméno může mít nejvýše 100 znaků."),
		],
	)
	email = StringField(
		"E-mail",
		filters=[lambda value: value.strip() if isinstance(value, str) else value],
		validators=[
			DataRequired(message="Vyplňte e-mail."),
			Email(message="Zadejte platnou e-mailovou adresu."),
			Length(max=254, message="E-mail může mít nejvýše 254 znaků."),
		],
	)
	answer = TextAreaField(
		"Vaše odpověď",
		filters=[lambda value: value.strip() if isinstance(value, str) else value],
		validators=[
			DataRequired(message="Vyplňte odpověď."),
			Length(max=5000, message="Odpověď může mít nejvýše 5000 znaků."),
		],
	)
	submit = SubmitField("Odeslat")

FORM = """<!doctype html>
<html lang="cs">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Dotazník</title>
  <style>
	body { max-width: 600px; margin: 3rem auto; padding: 0 1rem;
		   font: 16px system-ui, sans-serif; }
	label { display: block; margin: 1rem 0 .4rem; }
	input, textarea, button { box-sizing: border-box; width: 100%; padding: .7rem; }
	button { margin-top: 1rem; cursor: pointer; }
	.ok { color: green; }
	.errors { color: #b00020; margin: .35rem 0 0; padding-left: 1.25rem; }
  </style>
</head>
<body>
  <h1>Dotazník</h1>
  {% if sent %}<p class="ok">Děkujeme, odpověď byla uložena.</p>{% endif %}
  <form method="post" novalidate>
	{{ form.hidden_tag() }}
	{{ form.name.label }}
	{{ form.name(maxlength=100, required=true) }}
	{% if form.name.errors %}<ul class="errors">{% for error in form.name.errors %}<li>{{ error }}</li>{% endfor %}</ul>{% endif %}
	{{ form.email.label }}
	{{ form.email(type="email", maxlength=254, required=true) }}
	{% if form.email.errors %}<ul class="errors">{% for error in form.email.errors %}<li>{{ error }}</li>{% endfor %}</ul>{% endif %}
	{{ form.answer.label }}
	{{ form.answer(rows=5, maxlength=5000, required=true) }}
	{% if form.answer.errors %}<ul class="errors">{% for error in form.answer.errors %}<li>{{ error }}</li>{% endfor %}</ul>{% endif %}
	{{ form.submit() }}
  </form>
</body>
</html>"""

RESPONSES = """<!doctype html>
<html lang="cs">
<head>
	<meta charset="utf-8">
	<meta name="viewport" content="width=device-width, initial-scale=1">
	<title>Odpovědi dotazníku</title>
	<style>
		body { max-width: 1000px; margin: 3rem auto; padding: 0 1rem;
					 font: 16px system-ui, sans-serif; }
		table { width: 100%; border-collapse: collapse; }
		th, td { padding: .7rem; border-bottom: 1px solid #ccc; text-align: left;
						 vertical-align: top; }
		td.answer { white-space: pre-wrap; overflow-wrap: anywhere; }
	</style>
</head>
<body>
	<h1>Odpovědi dotazníku</h1>
	<p>Celkem odpovědí: {{ responses|length }} · <a href="/">Zpět na dotazník</a></p>
	{% if responses %}
	<table>
		<thead><tr><th>Datum</th><th>Jméno</th><th>E-mail</th><th>Odpověď</th></tr></thead>
		<tbody>
		{% for created_at, name, email, answer in responses %}
			<tr><td>{{ created_at }}</td><td>{{ name }}</td><td>{{ email }}</td>
					<td class="answer">{{ answer }}</td></tr>
		{% endfor %}
		</tbody>
	</table>
	{% else %}<p>Zatím tu nejsou žádné odpovědi.</p>{% endif %}
</body>
</html>"""


def init_database():
	"""Vytvoří databázi a tabulku odpovědí, pokud ještě neexistují."""
	connection_info = conninfo_to_dict(DATABASE_URL)
	database_name = connection_info.get("dbname", "postgres")
	admin_info = {**connection_info, "dbname": "postgres"}
	with closing(psycopg.connect(**admin_info, autocommit=True)) as connection:
		with connection.cursor() as cursor:
			cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database_name,))
			if cursor.fetchone() is None:
				cursor.execute(
					sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name))
				)

	with closing(psycopg.connect(DATABASE_URL)) as connection:
		with connection.cursor() as cursor:
			cursor.execute(
				"""CREATE TABLE IF NOT EXISTS questionnaire_responses (
					id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
					name VARCHAR(100) NOT NULL,
					email VARCHAR(254) NOT NULL,
					answer TEXT NOT NULL,
					created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
				)"""
			)
		connection.commit()


@app.route("/", methods=["GET", "POST"])
def questionnaire():
	form = QuestionnaireForm()
	if form.validate_on_submit():
		with closing(psycopg.connect(DATABASE_URL)) as connection:
			with connection.cursor() as cursor:
				cursor.execute(
					"INSERT INTO questionnaire_responses (name, email, answer) "
					"VALUES (%s, %s, %s)",
					(form.name.data, form.email.data, form.answer.data),
				)
			connection.commit()
		return redirect(url_for("questionnaire", sent="1"))

	return render_template_string(
		FORM, form=form, sent=request.args.get("sent") == "1"
	)


@app.route("/odpovedi")
def responses():
	with closing(psycopg.connect(DATABASE_URL)) as connection:
		with connection.cursor() as cursor:
			cursor.execute(
				"SELECT created_at, name, email, answer "
				"FROM questionnaire_responses ORDER BY created_at DESC"
			)
			rows = cursor.fetchall()
	return render_template_string(RESPONSES, responses=rows)


if __name__ == "__main__":
	init_database()
	app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
