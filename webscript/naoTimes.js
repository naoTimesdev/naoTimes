// Change this //
var gist_raw_url = 'MASUKAN URL RAW GIST TANPA REVISI COMMIT';
/////////////////

function nT_resolve_status(response) {
	if (response.status >= 200 && response.status < 300) {
		return Promise.resolve(response)
	} else {
		return Promise.reject(new Error(response.statusText))
	}
}

function nT_json_data(response) {
	return response.text();
}

function naoTimesProcess(disID) {
	console.log('Fetching naoTimes data');
	fetch(gist_raw_url)
	.then(nT_resolve_status)
	.then(nT_json_data)
	.then(function(nT_data) {
		var n = new Date();
		var formatDate = function formatDate(a) {
			var s = ((a * 1000) - n) / 1000;
			var m = Math.floor(s / 60);
			var h = Math.floor(s / 60 / 60);
			var d = Math.floor(s / 60 / 60 / 24);

			if (s < 0) {
				return false;
			}
	
			switch (d) {
				case 0:
					if (h > 1) {
						return 'Tayang dalam ' + h + ' jam';
					} else if (m > 1) {
						return 'Tayang dalam ' + m + ' menit';
					} else {
						return 'Tayang dalam ' + s + ' detik';
					}
				case 1:
					return 'Tayang besok';
				default:
					return 'Tayang dalam ' + d + ' hari';
			}
		};
		var div_data = document.getElementById("naotimes");
		var loading_elem = document.getElementById('naotimes-loading');
		var json_data = JSON.parse(nT_data)
		console.log('Parsing naoTimes data');
		var dis_data = json_data[disID];
        var available_anime = [];
        var word_replace = {"ENC": "Encode", "ED": "Edit", "TM": "Timing"};

		for (a in dis_data['anime']) {
			available_anime.push(a);
		}

		for (ava in available_anime) {
            var textRes = [];
            var current_episode = '';
            var status_list = dis_data['anime'][available_anime[ava]]['status'];
			for (stat in status_list) {
				if (status_list[stat]['status'] != 'released') {
                    current_episode += stat;
                    var ep_status = status_list[stat]['staff_status'];
                    for (key in ep_status) {
                        if (ep_status[key] == 'x') {
                            textRes.push(key);
                        }
                    }
					break;
				} else {
					continue;
				}
			}
			if (textRes == []) {
				continue;
			} else {
                textRes = textRes.join(" ");
                for (word in word_replace) {
                    textRes = textRes.replace(word, word_replace[word]);
                }
				get_time = formatDate(status_list[current_episode]['airing_time']);
				if (get_time != false) {
					textRes = get_time;
				}
				var h2_node = document.createElement("h2");
				h2_node.classList.add("naotimes-animetitle")
				var h2_textNode = document.createTextNode(available_anime[ava]);
				var stat_node = document.createElement("ul");
				stat_node.classList.add("naotimes-animeprogress")
				if (current_episode.length < 2) { // pad number
					var current_episode = '0' + current_episode;
				}
				var final_text = current_episode + ' @ ' + textRes;
				var stat_textNode = document.createTextNode(final_text);
				h2_node.appendChild(h2_textNode);
				stat_node.appendChild(stat_textNode);
				div_data.appendChild(h2_node);
				div_data.appendChild(stat_node);
			}
		}
		loading_elem.parentNode.removeChild(loading_elem);
		console.log('Finished!')
	}).catch(function(error) {
		console.log('Request failed', error);
	});
}