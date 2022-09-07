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
	fetch(`https://api.ihateani.me/utang/${disID}?pretty=1`)
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
		var json_data = JSON.parse(nT_data);
		if (json_data.length == 0) {
			var h2_node = document.createElement("h2");
			h2_node.classList.add("naotimes-animetitle")
			var h2_textNode = document.createTextNode("Tidak ada data utang");
			h2_node.appendChild(h2_textNode);
			loading_elem.parentNode.removeChild(loading_elem);
			return 0;
		}
		console.log('Parsing naoTimes data');
		json_data.forEach(function (item, index) {
			var statuses = item['status'];
			var current_stat = [];
			var current_episode = item['episode'];
			for (stat in statuses) {
				if (!statuses[stat]) {
					current_stat.push(stat);
				}
			}

			if (Array.isArray(current_stat) && current_stat.length) {
				current_stat = current_stat.join(" ");
				get_time = formatDate(item['airing_time']);
				if (get_time) {
					current_stat = get_time;
				}
				var h2_node = document.createElement("h2");
				h2_node.classList.add("naotimes-animetitle")
				var h2_textNode = document.createTextNode(item['title']);
				var stat_node = document.createElement("ul");
				stat_node.classList.add("naotimes-animeprogress")
				if (current_episode.length < 2) { // pad number
					var current_episode = '0' + current_episode;
				}
				var final_text = current_episode + ' @ ' + current_stat;
				var stat_textNode = document.createTextNode(final_text);
				h2_node.appendChild(h2_textNode);
				stat_node.appendChild(stat_textNode);
				div_data.appendChild(h2_node);
				div_data.appendChild(stat_node);
			}
		})
		loading_elem.parentNode.removeChild(loading_elem);
		console.log('Finished!')
	}).catch(function(error) {
		console.log('Request failed', error);
	});
}
