ART_NAME=demo
OUT_DIR=output
all: ${OUT_DIR}/${ART_NAME}.pdf show
PFL_FLAGS=--shell-escape -output-directory=${OUT_DIR}
dirs:
	mkdir -p output
	mkdir -p figures
clean:
	rm -rf figures
	rm -rf output
	rm -rf *~*

pdf: ${OUT_DIR}/${ART_NAME}.pdf

show: ${OUT_DIR}/${ART_NAME}.pdf
	evince ${OUT_DIR}/${ART_NAME}.pdf &

figures/done_multi: drawio.multi/*
	mkdir -p figures
	( cd drawio.multi ; ./do_layers.sh )
	touch figures/done_multi

	

${OUT_DIR}/${ART_NAME}.pdf: dirs figures/done_multi  *.tex parts/*.tex
	pdflatex ${PFL_FLAGS} ${ART_NAME}.tex
	pdflatex ${PFL_FLAGS} ${ART_NAME}.tex
	pdflatex ${PFL_FLAGS} ${ART_NAME}.tex
	
