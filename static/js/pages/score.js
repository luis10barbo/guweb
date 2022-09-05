new Vue({
    el:"#app",
    delimiters: ["<%", "%>"],
    data() {
        return {
            scoreId : scoreId,
            scoreInfo : {}
        }
    },
    created() {
        this.LoadScore(scoreId)
    },
    methods: {
        LoadScore(scoreId) {
            this.$set(this, 'scoreId', scoreId)

            const params = {
                id : this.scoreId
            }

            this.$axios.get(`${window.location.protocol}//api.${domain}/get_score_info`, { params }).then(res => {
                this.scoreInfo = res.data.leaderboard;
                // this.$set(this, 'load', false);
            });
            window.history.replaceState('', document.title, `/score/${this.scoreId}`);
        },
    },
    computed: {}
})