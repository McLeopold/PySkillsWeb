Skills = {};

Skills.get_contests = function () {
  $.getJSON('/contests/', function (data) {
    $('#main').html(JSON.stringify(data));
  });
}

Skills.setup = function () {
  $('#get_contests').click(Skills.get_contests);
}

$(function () {
  Skills.setup();
})
