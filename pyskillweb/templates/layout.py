from htmlr import *

doctype.html(
    head(lang="en")(
        meta(charset="utf-8"),
        title("{title}"),
        css('/static/style.css')
    ),
    body(
        section["main"],
        section["menu"](
            form(
                button(id='get_contests',value='Get Contests')
            )
        ),
        javascript('//ajax.googleapis.com/ajax/libs/jquery/1.7.1/jquery.min.js'),
        javascript('/static/skill.js')
    )
)

